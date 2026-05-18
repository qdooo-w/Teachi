"""
community.py - 社区技能广场路由

5 个端点：
- GET    /community/skills            列表（关键字搜索 + 分页 + 排序）
- GET    /community/skills/{id}       详情（元信息）
- POST   /community/skills            发布
- POST   /community/skills/{id}/install   一键安装到我的私有 skills 目录
- DELETE /community/skills/{id}       删除（仅作者）

发布与安装走 nonce 防重放（与 loop.py 同语义）。
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.config import BASE_DIR, DATABASE_PATH
from backend.db import DatabaseFacade
from backend.file import FileBase, FileError, ProjectFile, UserFile
from backend.skill_parser import (
    SkillParseError,
    parse_skill_file,
    validate_skill_name,
)


logger = logging.getLogger(__name__)
db = DatabaseFacade(db_path=DATABASE_PATH)
router = APIRouter(prefix="/community", tags=["community"])


# ── 响应/请求模型 ───────────────────────────────────────────────────────────────

class CommunitySkillSummary(BaseModel):
    """列表项：不含正文。"""
    id: str
    owner_uuid: str
    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    size_bytes: int
    downloads: int
    created_at: float
    updated_at: float


class CommunitySkillDetail(CommunitySkillSummary):
    """详情：技能内容本体在归档目录中，不通过 API 返回全文。"""
    pass


class CommunitySkillListResponse(BaseModel):
    skills: list[CommunitySkillSummary]
    total: int
    limit: int
    offset: int
    sort: Literal["popular", "newest"]


class PublishSkillRequest(BaseModel):
    """发布请求。后端从当前用户的 skills/<skill_name>/ 复制整个目录。"""
    skill_name: str = Field(..., min_length=1, max_length=64)


class InstallSkillRequest(BaseModel):
    """安装目标。默认安装到当前用户的私有 skills 目录。"""
    target: Literal["user", "project"] = "user"
    pid: str | None = None


class InstallResponse(BaseModel):
    name: str
    skill_id: str
    downloads: int


# ── 工具函数 ───────────────────────────────────────────────────────────────────

def _to_summary(record: dict) -> CommunitySkillSummary:
    return CommunitySkillSummary(
        id=record["id"],
        owner_uuid=record["owner_uuid"],
        name=record["name"],
        description=record["description"],
        license=record.get("license"),
        compatibility=record.get("compatibility"),
        size_bytes=int(record["size_bytes"]),
        downloads=int(record["downloads"]),
        created_at=float(record["created_at"]),
        updated_at=float(record["updated_at"]),
    )


def _to_detail(record: dict) -> CommunitySkillDetail:
    return CommunitySkillDetail(**_to_summary(record).model_dump())


def _archive_root() -> Path:
    root = (BASE_DIR / "archived_skill").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _archive_rel_path(skill_id: str) -> str:
    return f"archived_skill/{skill_id}"


def _resolve_archive_path(archive_path: str) -> Path:
    root = _archive_root()
    target = (BASE_DIR / archive_path).resolve()
    if target != root and root not in target.parents:
        raise FileError("Archived skill path is outside archived_skill directory.")
    return target


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _copy_skill_dir(src: Path, dst: Path) -> None:
    if not src.is_dir():
        raise FileError("Skill folder not found")
    if dst.exists():
        raise FileError("Target skill folder already exists")
    try:
        shutil.copytree(src, dst)
    except Exception as e:
        raise FileError(str(e)) from e


def _install_target_fs(
    payload: InstallSkillRequest,
    user_uuid: str,
) -> FileBase:
    if payload.target == "project":
        if not payload.pid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "VALIDATION_ERROR", "message": "pid is required when target is project"},
            )
        try:
            return ProjectFile(pid=payload.pid, user_uuid=user_uuid, db_facade=db)
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
            )

    try:
        return UserFile(user_uuid=user_uuid, db_facade=db)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access denied"},
        )


# ── 路由 ───────────────────────────────────────────────────────────────────────

@router.get("/skills", response_model=CommunitySkillListResponse)
def list_community_skills(
    keyword: str | None = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: Literal["popular", "newest"] = Query("popular"),
    _user: dict[str, Any] = Depends(get_current_user),
) -> CommunitySkillListResponse:
    """社区列表。默认按 downloads 降序（并列时 created_at 兜底）。"""
    skills = db.community.list(keyword=keyword, limit=limit, offset=offset, sort=sort)
    total = db.community.count(keyword=keyword)
    return CommunitySkillListResponse(
        skills=[_to_summary(s) for s in skills],
        total=total,
        limit=limit,
        offset=offset,
        sort=sort,
    )


@router.get("/skills/{skill_id}", response_model=CommunitySkillDetail)
def get_community_skill(
    skill_id: str,
    _user: dict[str, Any] = Depends(get_current_user),
) -> CommunitySkillDetail:
    """详情。"""
    record = db.community.get_by_id(skill_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Community skill not found"},
        )
    return _to_detail(record)


@router.post(
    "/skills",
    response_model=CommunitySkillDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_nonce)],
)
def publish_community_skill(
    payload: PublishSkillRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CommunitySkillDetail:
    """发布 skill 到社区。

    - 后端从当前用户 skills/<skill_name>/ 复制整个目录到 archived_skill/{id}/
    - 后端**重新解析** SKILL.md frontmatter，不信任前端元信息
    - 同一作者可重复发布同名 skill：每次都是独立条目
    """
    skill_name = payload.skill_name.strip()
    if name_err := validate_skill_name(skill_name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": f"skill_name 不合法：{name_err}"},
        )

    try:
        user_fs = UserFile(user_uuid=current_user["uuid"], db_facade=db)
        skill_dir = user_fs._safe_path(f"skills/{skill_name}")
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access denied"},
        )
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )

    if not skill_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Skill folder not found"},
        )

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": "技能文件夹缺少 SKILL.md"},
        )

    try:
        fields = parse_skill_file(skill_md.read_text(encoding="utf-8"))
    except SkillParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": str(e)},
        )
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": f"SKILL.md 必须是 UTF-8 文本：{e}"},
        )

    if fields.name != skill_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "SKILL_PARSE_ERROR",
                "message": "SKILL.md frontmatter.name 必须与技能文件夹名一致",
            },
        )

    owner_uuid = current_user["uuid"]
    skill_id = str(uuid.uuid4())
    archive_rel_path = _archive_rel_path(skill_id)
    archive_dir = _resolve_archive_path(archive_rel_path)
    try:
        _copy_skill_dir(skill_dir, archive_dir)
        record = db.community.create(
            skill_id=skill_id,
            owner_uuid=owner_uuid,
            name=fields.name,
            description=fields.description,
            archive_path=archive_rel_path,
            size_bytes=_directory_size(archive_dir),
            license=fields.license,
            compatibility=fields.compatibility,
        )
    except FileError as e:
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        ) from e
    except Exception:
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
        raise
    logger.info("community_skill_published id=%s name=%s owner=%s", record["id"], fields.name, owner_uuid)
    return _to_detail(record)


@router.post(
    "/skills/{skill_id}/install",
    response_model=InstallResponse,
    dependencies=[Depends(verify_nonce)],
)
def install_community_skill(
    skill_id: str,
    payload: InstallSkillRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> InstallResponse:
    """把社区 skill 安装到用户级或项目级 skills/{name}/。

    - 本地已存在同名目录（不论是否含 SKILL.md）→ 409，由用户改名后重试
    - 安装成功后社区记录 downloads += 1
    """
    payload = payload or InstallSkillRequest()
    record = db.community.get_by_id(skill_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Community skill not found"},
        )

    user_uuid = current_user["uuid"]
    name = record["name"]

    # 信任但验证：DB 中的 name 应已通过 publish 层校验，但仍兜底防御历史脏数据
    if validate_skill_name(name) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SKILL_NAME", "message": "Skill name in record is not safe"},
        )

    target_fs = _install_target_fs(payload, user_uuid)

    # 目录冲突检测：直接看 skills/{name} 目录是否已存在
    try:
        skill_dir = target_fs._safe_path(f"skills/{name}")
    except FileError:
        # name 含非法路径字符——理论上 publish 时已通过 validate_skill_name 拦截
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SKILL_NAME", "message": "Skill name is not safe"},
        )
    if skill_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOCAL_SKILL_EXISTS",
                "message": f"本地已存在同名技能 {name!r}，请先重命名或删除后重试。",
            },
        )

    try:
        archive_dir = _resolve_archive_path(record["archive_path"])
        if not archive_dir.is_dir():
            raise FileError("Archived skill folder not found")
        _copy_skill_dir(archive_dir, skill_dir)
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )

    db.community.increment_downloads(skill_id)
    refreshed = db.community.get_by_id(skill_id)
    downloads = int(refreshed["downloads"]) if refreshed else int(record["downloads"]) + 1
    logger.info("community_skill_installed id=%s name=%s user=%s", skill_id, name, user_uuid)
    return InstallResponse(name=name, skill_id=skill_id, downloads=downloads)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community_skill(
    skill_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """删除社区 skill，仅作者可调用。"""
    record = db.community.get_by_id(skill_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Community skill not found"},
        )
    if record["owner_uuid"] != current_user["uuid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only the author can delete this skill"},
        )
    try:
        archive_dir = _resolve_archive_path(record["archive_path"])
        if archive_dir.exists():
            shutil.rmtree(archive_dir)
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )
    if not db.community.delete_for_owner(skill_id, current_user["uuid"]):
        # 极端竞态：刚才存在，DELETE 之间被别人删了；按 404 处理更直观
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Community skill not found"},
        )
