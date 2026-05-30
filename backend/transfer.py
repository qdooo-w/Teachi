"""
transfer.py - 大文件传输路由模块

当前职责：
1. 处理社区技能 zip 上传（原始二进制）
2. 校验 zip 结构与内容白名单
3. 解析 SKILL.md 并入库发布
"""

from __future__ import annotations

import shutil
import uuid
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.auth import get_current_user, verify_nonce
from backend.config import (
    BASE_DIR,
    DATABASE_PATH,
    SKILL_TEXT_EXTENSIONS,
    SKILL_ZIP_ALLOWED_CONTENT_TYPES,
    SKILL_ZIP_MAX_BYTES,
    SKILL_ZIP_RESOURCE_DIR_ALIASES,
)
from backend.db import DatabaseFacade
from backend.file import FileError
from backend.skill_parser import SkillFields, SkillParseError, parse_skill_file


db = DatabaseFacade(db_path=DATABASE_PATH)
router = APIRouter(tags=["transfer"])


class CommunitySkillDetail(BaseModel):
    id: str
    owner_uuid: str
    name: str
    display_name: str | None = None
    description: str
    license: str | None = None
    compatibility: str | None = None
    size_bytes: int
    downloads: int
    created_at: float
    updated_at: float


def _community_skill_detail(record: dict[str, Any]) -> CommunitySkillDetail:
    return CommunitySkillDetail(
        id=str(record["id"]),
        owner_uuid=str(record["owner_uuid"]),
        name=str(record["name"]),
        display_name=record.get("display_name"),
        description=str(record["description"]),
        license=record.get("license"),
        compatibility=record.get("compatibility"),
        size_bytes=int(record["size_bytes"]),
        downloads=int(record["downloads"]),
        created_at=float(record["created_at"]),
        updated_at=float(record["updated_at"]),
    )


def _community_archive_root() -> Path:
    root = (BASE_DIR / "archived_skill").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _community_archive_rel_path(skill_id: str) -> str:
    return f"archived_skill/{skill_id}"


def _resolve_community_archive_path(archive_path: str) -> Path:
    root = _community_archive_root()
    target = (BASE_DIR / archive_path).resolve()
    if target != root and root not in target.parents:
        raise FileError("Archived skill path is outside archived_skill directory.")
    return target


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _zip_validation_error(message: str, status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": "ZIP_VALIDATION_ERROR", "message": message},
    )


def _community_zip_size_label() -> str:
    mb = SKILL_ZIP_MAX_BYTES / (1024 * 1024)
    return f"{mb:g} MB"


def _zip_entry_parts(raw_name: str) -> tuple[str, ...]:
    if not raw_name or "\x00" in raw_name:
        _zip_validation_error("Zip entry path is empty or contains NUL byte.")
    if raw_name.startswith("/") or raw_name.startswith("\\"):
        _zip_validation_error("Zip entry paths must be relative.")

    normalized = raw_name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", "..", "/"} for part in parts):
        _zip_validation_error("Zip entry paths must not contain empty, '.', '..', or absolute segments.")
    return tuple(parts)


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _validate_skill_zip_relpath(parts: tuple[str, ...]) -> tuple[str, ...]:
    if parts == ("SKILL.md",):
        return parts

    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
    suffix = Path(parts[-1]).suffix.lower()
    is_image = suffix in image_extensions

    if len(parts) == 1:
        if not is_image and suffix not in SKILL_TEXT_EXTENSIONS:
            _zip_validation_error("Skill zip root files must be md, txt, json, yaml, or yml text files.")
        return parts

    folder = parts[0]
    normalized_folder = SKILL_ZIP_RESOURCE_DIR_ALIASES.get(folder)
    if normalized_folder is None:
        _zip_validation_error("Skill zip folders can only be reference(s)/ or assets/.")
    if not is_image and suffix not in SKILL_TEXT_EXTENSIONS:
        _zip_validation_error("Skill zip resource files must be md, txt, json, yaml, or yml text files.")
    return (normalized_folder,) + parts[1:]


def _validate_community_skill_zip(
    zip_file: zipfile.ZipFile,
) -> tuple[SkillFields, list[tuple[zipfile.ZipInfo, tuple[str, ...]]]]:
    raw_entries = zip_file.infolist()
    if not raw_entries:
        _zip_validation_error("Zip file is empty.")

    file_entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    dir_entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    total_uncompressed = 0
    for info in raw_entries:
        parts = _zip_entry_parts(info.filename)
        if _is_zip_symlink(info):
            _zip_validation_error("Zip file must not contain symbolic links.")
        if info.flag_bits & 0x1:
            _zip_validation_error("Encrypted zip entries are not supported.")
        if info.is_dir():
            dir_entries.append((info, parts))
            continue
        total_uncompressed += int(info.file_size)
        if total_uncompressed > SKILL_ZIP_MAX_BYTES:
            _zip_validation_error(
                f"Uncompressed zip content must not exceed {_community_zip_size_label()}.",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        file_entries.append((info, parts))

    if not file_entries:
        _zip_validation_error("Zip file does not contain any files.")

    has_root_skill = any(parts == ("SKILL.md",) for _info, parts in file_entries)
    strip_root: tuple[str, ...] = ()
    if not has_root_skill:
        top_level = {parts[0] for _info, parts in file_entries}
        if len(top_level) != 1:
            _zip_validation_error("Zip must contain SKILL.md at root or one top-level skill folder.")
        strip_root = (next(iter(top_level)),)

    normalized_entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    seen_paths: set[tuple[str, ...]] = set()
    skill_md_info: zipfile.ZipInfo | None = None
    for _info, parts in dir_entries:
        rel_parts = parts[len(strip_root):] if strip_root else parts
        if not rel_parts:
            continue
        if len(rel_parts) < 1 or rel_parts[0] not in SKILL_ZIP_RESOURCE_DIR_ALIASES:
            _zip_validation_error("Skill zip directories can only be reference(s)/ or assets/.")

    for info, parts in file_entries:
        rel_parts = parts[len(strip_root):] if strip_root else parts
        if not rel_parts:
            continue
        normalized_rel_parts = _validate_skill_zip_relpath(rel_parts)
        if normalized_rel_parts in seen_paths:
            _zip_validation_error(f"Duplicate zip entry: {'/'.join(normalized_rel_parts)}")
        seen_paths.add(normalized_rel_parts)
        if normalized_rel_parts == ("SKILL.md",):
            skill_md_info = info
        normalized_entries.append((info, normalized_rel_parts))

    if skill_md_info is None:
        _zip_validation_error("Skill zip must contain SKILL.md.")

    try:
        skill_md = zip_file.read(skill_md_info).decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": f"SKILL.md 必须是 UTF-8 文本：{e}"},
        ) from e
    except RuntimeError as e:
        _zip_validation_error(f"Failed to read SKILL.md from zip: {e}")

    try:
        fields = parse_skill_file(skill_md)
    except SkillParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": str(e)},
        ) from e

    return fields, normalized_entries


def _extract_community_skill_zip(
    zip_file: zipfile.ZipFile,
    entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]],
    target_dir: Path,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=False)
    for info, rel_parts in entries:
        target = (target_dir / Path(*rel_parts)).resolve()
        if target != target_dir and target_dir not in target.parents:
            raise FileError("Zip entry resolved outside target directory.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(info) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)


async def _read_limited_zip_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > SKILL_ZIP_MAX_BYTES:
                _zip_validation_error(
                    f"Zip file must not exceed {_community_zip_size_label()}.",
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_CONTENT_LENGTH", "message": "Invalid Content-Length header"},
            ) from e

    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > SKILL_ZIP_MAX_BYTES:
            _zip_validation_error(
                f"Zip file must not exceed {_community_zip_size_label()}.",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        chunks.append(chunk)

    body = b"".join(chunks)
    if not body:
        _zip_validation_error("Zip file is required.")
    return body


@router.post(
    "/community/skills/upload",
    response_model=CommunitySkillDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_nonce)],
)
async def upload_community_skill_zip(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CommunitySkillDetail:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in SKILL_ZIP_ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "UNSUPPORTED_FILE_TYPE", "message": "Only zip uploads are supported"},
        )

    body = await _read_limited_zip_body(request)
    if not zipfile.is_zipfile(BytesIO(body)):
        _zip_validation_error("Uploaded file must be a valid zip archive.")

    owner_uuid = current_user["uuid"]
    skill_id = str(uuid.uuid4())
    archive_rel_path = _community_archive_rel_path(skill_id)
    archive_dir = _resolve_community_archive_path(archive_rel_path)

    try:
        with zipfile.ZipFile(BytesIO(body)) as zip_file:
            fields, entries = _validate_community_skill_zip(zip_file)
            _extract_community_skill_zip(zip_file, entries, archive_dir)

        record = db.community.create(
            skill_id=skill_id,
            owner_uuid=owner_uuid,
            name=fields.name,
            display_name=fields.display_name,
            description=fields.description,
            archive_path=archive_rel_path,
            size_bytes=_directory_size(archive_dir),
            license=fields.license,
            compatibility=fields.compatibility,
        )
    except HTTPException:
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, FileError) as e:
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ZIP_VALIDATION_ERROR", "message": str(e)},
        ) from e
    except Exception:
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
        raise

    return _community_skill_detail(record)
