from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.config import BASE_DIR
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from backend.file import FileError, ProjectFile, UserFile, LibraryFile
from backend.skill_parser import (
    SkillParseError,
    parse_skill_file,
    validate_skill_name,
)
from backend.community import _archive_root

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/library", tags=["library"])

def _resolve_db(db_param: Any) -> DatabaseFacade:
    if isinstance(db_param, DatabaseFacade):
        return db_param
    global_db = globals().get("db")
    if isinstance(global_db, DatabaseFacade):
        return global_db
    raise RuntimeError("DatabaseFacade not initialized in library module")

def _archive_rel_path(skill_id: str, version: str) -> str:
    return f"archived_skill/{skill_id}/{version}"

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

def _suggest_next_version(current: str | None) -> str:
    """将版本号末位加一，用于预填发布表单的建议版本。"""
    if not current:
        return "1.0.0"
    parts = current.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    except (ValueError, IndexError):
        return "1.0.0"

class CollectSkillRequest(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=64)

class PublishFromLibraryRequest(BaseModel):
    version: str = Field(..., pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    changelog: str = ""

class InstallFromLibraryRequest(BaseModel):
    target: Literal["user", "project"] = "user"
    pid: str | None = None

@router.get("/skills/parse-runtime")
def parse_runtime_skill(
    skill_name: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """读取本地技能配置以辅助填充表单"""
    db = _resolve_db(db)
    if name_err := validate_skill_name(skill_name):
        raise HTTPException(status_code=400, detail={"code": "INVALID_NAME", "message": name_err})
    
    try:
        user_fs = UserFile(user_uuid=current_user["uuid"], db_facade=db)
        skill_dir = user_fs._safe_path(f"skills/{skill_name}")
    except PermissionError:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Access denied"})
        
    if not skill_dir.is_dir():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Skill not found"})
        
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise HTTPException(status_code=422, detail={"code": "NO_SKILL_MD", "message": "Missing SKILL.md"})
        
    try:
        fields = parse_skill_file(skill_md.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=422, detail={"code": "PARSE_ERROR", "message": str(e)})

    # Check if we already have this in library
    latest_lib = db.library.get_latest_by_name(user_uuid=current_user["uuid"], name=skill_name)
    
    return {
        "frontmatter": fields.model_dump(),
        "latest_in_library": latest_lib
    }

@router.post("/skills/collect", dependencies=[Depends(verify_nonce)])
def collect_skill_to_library(
    payload: CollectSkillRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """收集操作：从运行层 skills/{name} 复制到 library/{library_id}/skill/"""
    db = _resolve_db(db)
    skill_name = payload.skill_name.strip()
    if name_err := validate_skill_name(skill_name):
        raise HTTPException(status_code=400, detail={"code": "INVALID_NAME", "message": name_err})
        
    user_uuid = current_user["uuid"]
    try:
        user_fs = UserFile(user_uuid=user_uuid, db_facade=db)
        src_dir = user_fs._safe_path(f"skills/{skill_name}")
    except PermissionError:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Access denied"})
        
    if not src_dir.is_dir():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Skill not found"})
        
    skill_md = src_dir / "SKILL.md"
    if not skill_md.is_file():
        raise HTTPException(status_code=422, detail={"code": "NO_SKILL_MD", "message": "Missing SKILL.md"})
        
    try:
        fields = parse_skill_file(skill_md.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=422, detail={"code": "PARSE_ERROR", "message": str(e)})

    library_id = str(uuid.uuid4())
    library_fs = LibraryFile(library_id=library_id, user_uuid=user_uuid, db_facade=db)
    dst_dir = library_fs.base_path / "skill"
    
    try:
        _copy_skill_dir(src_dir, dst_dir)
        readme_path = dst_dir / "README.md"
        readme_content = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
        
        record = db.library.create(
            user_uuid=user_uuid,
            name=fields.name,
            display_name=fields.display_name,
            description=fields.description,
            readme_md=readme_content,
            tags="[]",
            version="1.0.0",
            changelog="Initial collect",
            source="runtime",
            community_skill_id=None,
            local_path=f"data/{user_uuid}/library/{library_id}",
            size_bytes=_directory_size(dst_dir),
            skill_id=library_id
        )
        return record
    except Exception as e:
        if dst_dir.parent.exists():
            shutil.rmtree(dst_dir.parent, ignore_errors=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})

@router.get("/skills")
def list_library_skills(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    return db.library.list_by_user(current_user["uuid"])

@router.post("/skills/{library_id}/publish", dependencies=[Depends(verify_nonce)])
def publish_from_library(
    library_id: str,
    payload: PublishFromLibraryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """发布操作：将 library 中的技能发布至社区"""
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    
    lib_record = db.library.get_by_id(library_id)
    if not lib_record or lib_record["user_uuid"] != user_uuid:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})
        
    library_fs = LibraryFile(library_id=library_id, user_uuid=user_uuid, db_facade=db)
    src_dir = library_fs.base_path / "skill"
    
    if not src_dir.is_dir():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill data missing"})
        
    community_skill_id = lib_record["community_skill_id"]
    if not community_skill_id:
        import json
        admin_uuids = json.dumps([user_uuid])
        skill_record = db.community.create_skill(
            skill_id=str(uuid.uuid4()),
            owner_uuid=user_uuid,
            name=lib_record["name"],
            display_name=lib_record["display_name"],
            description=lib_record["description"],
            admin_uuids=admin_uuids
        )
        community_skill_id = skill_record["id"]
        
        db.library.update_community_skill_id(library_id, community_skill_id)
            
    archive_rel = _archive_rel_path(community_skill_id, payload.version)
    dst_dir = _resolve_archive_path(archive_rel) / "skill"
    
    try:
        dst_dir.parent.mkdir(parents=True, exist_ok=True)
        _copy_skill_dir(src_dir, dst_dir)
        
        version_record = db.community.create_version(
            version_id=library_id,
            skill_id=community_skill_id,
            version=payload.version,
            readme_md=lib_record["readme_md"],
            changelog=payload.changelog,
            tags=lib_record["tags"],
            archive_path=archive_rel,
            size_bytes=_directory_size(dst_dir),
            source="library",
            status="PENDING_OWNER",
            submitted_by=user_uuid
        )
        return version_record
    except Exception as e:
        if dst_dir.parent.exists():
            shutil.rmtree(dst_dir.parent, ignore_errors=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})

@router.get("/skills/{library_id}")
def get_library_skill(
    library_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """获取单条仓库 skill 详情。"""
    db = _resolve_db(db)
    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})
    return record

@router.get("/skills/{library_id}/template")
def get_library_skill_template(
    library_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """按 skill name 查找社区同名已上架条目，供用户选择发布模板（关联已有社区条目或新建）。"""
    db = _resolve_db(db)
    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})
    matched = db.community.get_skill_by_name(record["name"])
    return {
        "library_skill": record,
        "matched_community_skill": matched,
    }

@router.get("/skills/{library_id}/publish-form")
def get_publish_form(
    library_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """预填发布表单：返回仓库 skill 数据、已关联社区条目及建议版本号。"""
    db = _resolve_db(db)
    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})
    community_skill = None
    latest_version = None
    if record["community_skill_id"]:
        community_skill = db.community.get_skill(record["community_skill_id"])
        latest_version = db.community.get_latest_approved_version(record["community_skill_id"])
    return {
        "library_skill": record,
        "community_skill": community_skill,
        "latest_approved_version": latest_version,
        "suggested_version": _suggest_next_version(latest_version["version"] if latest_version else None),
    }

@router.post("/skills/{library_id}/install", dependencies=[Depends(verify_nonce)])
def install_from_library(
    library_id: str,
    payload: InstallFromLibraryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """仓库→运行层安装：将 library/{library_id}/skill/ 复制到 skills/{name}/，无 DB 写入。"""
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    lib_record = db.library.get_by_id(library_id)
    if not lib_record or lib_record["user_uuid"] != user_uuid:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})
    library_fs = LibraryFile(library_id=library_id, user_uuid=user_uuid, db_facade=db)
    src_dir = library_fs.base_path / "skill"
    if not src_dir.is_dir():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill data missing"})
    name = lib_record["name"]
    if payload.target == "project":
        if not payload.pid:
            raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "pid is required"})
        try:
            target_fs = ProjectFile(pid=payload.pid, user_uuid=user_uuid, db_facade=db)
        except PermissionError:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Project not found"})
    else:
        try:
            target_fs = UserFile(user_uuid=user_uuid, db_facade=db)
        except PermissionError:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Access denied"})
    try:
        dst_dir = target_fs._safe_path(f"skills/{name}")
    except FileError:
        raise HTTPException(status_code=400, detail={"code": "INVALID_NAME", "message": "Invalid skill name"})
    if dst_dir.exists():
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "Skill already exists in target location"})
    try:
        _copy_skill_dir(src_dir, dst_dir)
    except FileError as e:
        raise HTTPException(status_code=400, detail={"code": "FILE_ERROR", "message": str(e)})
    return {"name": name, "target": payload.target, "installed": True}
