from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.community.utils import (
    resolve_db as _resolve_db,
    archive_root as _archive_root,
    resolve_archive_path as _resolve_archive_path,
    copy_skill_dir as _copy_skill_dir,
    directory_size as _directory_size,
)
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from backend.file import FileError, ProjectFile, UserFile, LibraryFile
from backend.skill_parser import (
    SkillParseError,
    parse_skill_file,
    validate_skill_name,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/library", tags=["library"])


def _archive_rel_path(skill_id: str, version: str) -> str:
    return f"archived_skill/{skill_id}/{version}"


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
    template_id: str | None = None  # 可选：指定模板技能 ID
    name: str | None = Field(None, min_length=1, max_length=64)
    display_name: str | None = None
    description: str | None = None
    readme_md: str | None = None
    tags: str | None = None

class UpdateLibrarySkillMetaRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    display_name: str | None = None
    description: str | None = None
    readme_md: str | None = None
    tags: str | None = None

class PublishFromLibraryRequest(BaseModel):
    version: str = Field(..., pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    changelog: str = ""

class InstallFromLibraryRequest(BaseModel):
    target: Literal["user", "project"] = "user"
    pid: str | None = None


LibrarySkillSort = Literal["newest", "oldest", "name-asc", "name-desc"]


class LibrarySkillListResponse(BaseModel):
    skills: list[dict]
    total: int
    limit: int
    offset: int
    sort: str

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

    readme_path = skill_dir / "README.md"
    readme_content = ""
    if readme_path.is_file():
        try:
            readme_content = readme_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            readme_content = ""

    return {
        "frontmatter": asdict(fields),
        "readme_md": readme_content,
        "latest_in_library": latest_lib,
    }


@router.get("/skills/match-template")
def match_template(
    skill_name: str = Query(..., min_length=1, max_length=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """根据 skill_name 在仓库中查找最佳匹配的模板技能。

    返回同名的仓库技能（如有），用于收集时预填元数据。
    """
    db = _resolve_db(db)
    matched = db.library.get_latest_by_name(user_uuid=current_user["uuid"], name=skill_name)
    return {
        "skill_name": skill_name,
        "matched": matched,  # 可能为 null
    }


@router.post("/skills/collect", dependencies=[Depends(verify_nonce)])
def collect_skill_to_library(
    payload: CollectSkillRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    收集操作：从运行层 skills/{name} 复制到 library/{library_id}/skill/
    
    【数据流】
    - 输入：Payload 中的运行层技能名称 (skill_name) 和可选的 template_id
    - 模板匹配：优先使用 template_id 指定的模板，否则查找仓库中同名技能作为最佳匹配
    - 文件流：读取 data/{user_uuid}/skills/{skill_name} -> 复制到 data/{user_uuid}/library/{library_id}/skill/
    - 数据库流：在 user_library_skills 表中新建一条记录，元数据从模板继承（如有）

    【调用链】
    - 客户端请求 -> APIRouter -> collect_skill_to_library()
    - 获取当前用户 -> get_current_user()
    - 初始化文件系统管理器 -> UserFile, LibraryFile (file.py)
    - 解析 SKILL.md -> parse_skill_file() (skill_parser.py)
    - 模板匹配 -> db.library.get_by_id() 或 db.library.get_latest_by_name()
    - 文件复制 -> _copy_skill_dir()
    - 创建数据库记录 -> db.library.create() (db.py::UserLibrarySkillsFacade)
    """
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

    # 模板匹配：优先使用指定的 template_id，否则查找同名技能
    template = None
    if payload.template_id:
        template = db.library.get_by_id(payload.template_id)
        if template and template["user_uuid"] != user_uuid:
            template = None  # 不允许使用其他用户的模板
    if not template:
        template = db.library.get_latest_by_name(user_uuid=user_uuid, name=skill_name)

    # 从模板继承元数据，无模板时使用默认值，如果 payload 传入了则优先使用
    display_name = payload.display_name if payload.display_name is not None else (template["display_name"] if template else fields.display_name)
    description = payload.description if payload.description is not None else (template["description"] if template else "")
    readme_md = payload.readme_md if payload.readme_md is not None else (template["readme_md"] if template else (fields.body if fields.body else ""))
    tags = payload.tags if payload.tags is not None else (template["tags"] if template else "[]")
    
    # 优先使用 SKILL.md 中解析出来的 version，其次继承模板版本，最后默认为 "1.0.0"
    version = fields.version if fields.version else (template["version"] if template else "1.0.0")

    library_id = str(uuid.uuid4())
    library_fs = LibraryFile(library_id=library_id, user_uuid=user_uuid, db_facade=db)
    dst_dir = library_fs.base_path / "skill"

    try:
        _copy_skill_dir(src_dir, dst_dir)

        final_name = payload.name.strip() if (payload.name and payload.name.strip()) else fields.name

        record = db.library.create(
            user_uuid=user_uuid,
            name=final_name,
            display_name=display_name,
            description=description,
            readme_md=readme_md,
            tags=tags,
            version=version,
            changelog="Initial collect",
            source="runtime",
            community_skill_id=None,  # 为空表示来自运行层
            local_path=f"data/{user_uuid}/library/{library_id}",
            size_bytes=_directory_size(dst_dir),
            skill_id=library_id
        )
        return record
    except Exception as e:
        if dst_dir.parent.exists():
            shutil.rmtree(dst_dir.parent, ignore_errors=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})

class ForkLibrarySkillRequest(BaseModel):
    """Fork 时可选覆盖元数据，不传则继承源记录"""
    name: str | None = Field(None, min_length=1, max_length=64)
    display_name: str | None = None
    description: str | None = None
    readme_md: str | None = None
    tags: str | None = None

@router.post("/skills/{library_id}/fork", dependencies=[Depends(verify_nonce)])
def fork_library_skill(
    library_id: str,
    payload: ForkLibrarySkillRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    Fork 操作：从仓库层复制一份技能到新仓库条目（不经过运行层）

    【数据流】
    - 输入：源仓库技能 ID (library_id)，可选覆盖元数据
    - 文件流：library/{old_id}/skill/ -> 复制到 library/{new_id}/skill/
    - 数据库流：继承源记录的元数据和 version，payload 中的字段优先覆盖

    【调用链】
    - 客户端请求 -> APIRouter -> fork_library_skill()
    - 校验源记录归属 -> db.library.get_by_id()
    - 文件复制 -> _copy_skill_dir()
    - 创建数据库记录 -> db.library.create()
    """
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]

    src_record = db.library.get_by_id(library_id)
    if not src_record or src_record["user_uuid"] != user_uuid:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})

    src_dir = LibraryFile(library_id=library_id, user_uuid=user_uuid, db_facade=db).base_path / "skill"
    if not src_dir.is_dir():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill data missing"})

    # payload 传入的字段覆盖源记录
    p = payload or ForkLibrarySkillRequest()
    name = p.name.strip() if p.name else src_record["name"]
    display_name = p.display_name if p.display_name is not None else src_record["display_name"]
    description = p.description if p.description is not None else src_record["description"]
    readme_md = p.readme_md if p.readme_md is not None else src_record["readme_md"]
    tags = p.tags if p.tags is not None else src_record["tags"]
    version = src_record["version"]  # 版本号继承自源记录

    new_id = str(uuid.uuid4())
    dst_dir = LibraryFile(library_id=new_id, user_uuid=user_uuid, db_facade=db).base_path / "skill"

    try:
        _copy_skill_dir(src_dir, dst_dir)

        record = db.library.create(
            user_uuid=user_uuid,
            name=name,
            display_name=display_name,
            description=description,
            readme_md=readme_md,
            tags=tags,
            version=version,
            changelog="Fork",
            source="fork",
            community_skill_id=src_record["community_skill_id"],
            local_path=f"data/{user_uuid}/library/{new_id}",
            size_bytes=_directory_size(dst_dir),
            skill_id=new_id,
        )
        return record
    except Exception as e:
        if dst_dir.parent.exists():
            shutil.rmtree(dst_dir.parent, ignore_errors=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})

@router.get("/skills")
def list_library_skills(
    keyword: str | None = Query(None, max_length=200, description="搜索关键词（匹配名称/显示名/描述）"),
    tag: list[str] = Query(default=[], max_length=50, description="标签筛选（可多选，AND 逻辑）"),
    sort: LibrarySkillSort = Query("newest", description="排序方式"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="起始偏移"),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """获取当前用户仓库技能列表，支持关键词/标签筛选、排序与分页"""
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]

    skills = db.library.list_by_user_filtered(
        user_uuid=user_uuid,
        keyword=keyword,
        tags=tag if tag else None,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    total = db.library.count_by_user(user_uuid=user_uuid, keyword=keyword, tags=tag if tag else None)

    return {
        "skills": skills,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort,
    }

@router.post("/skills/{library_id}/publish", dependencies=[Depends(verify_nonce)])
def publish_from_library(
    library_id: str,
    payload: PublishFromLibraryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    发布操作：将 library 中的技能发布至社区（两阶段审核流第一步）
    
    【数据流】
    - 输入：仓库技能 ID (library_id), 目标版本号 (version) 及变更说明 (changelog)
    - 关联检查：如果该仓库技能没有绑定社区技能 ID，则新建社区技能主表记录（owner 设为当前用户，admin_uuids 包含当前用户），并同步双写管理员子表；接着将更新写回仓库表的 community_skill_id 列。
    - 文件流：从仓库技能目录 data/{user_uuid}/library/{library_id}/skill/ -> 复制到社区归档目录 archived_skill/{community_skill_id}/{version}/skill/
    - 数据库流：在 community_skill_versions 表中创建待审核版本，status 初始为 'PENDING_OWNER'，等候技能管理员或全局管理员审批。
    
    【调用链】
    - 客户端请求 -> APIRouter -> publish_from_library()
    - 校验仓库记录归属 -> db.library.get_by_id() (db.py)
    - 若无绑定，初始化社区主表 -> db.community.create_skill() (db.py::CommunitySkillsFacade)
    - 反向更新仓库绑定 -> db.library.update_community_skill_id() (db.py::UserLibrarySkillsFacade)
    - 初始化文件系统 -> LibraryFile, _resolve_archive_path() (file.py / library.py)
    - 文件复制 -> _copy_skill_dir()
    - 创建待审版本记录 -> db.community.create_version() (db.py::CommunitySkillsFacade)
    """
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
    """
    仓库→运行层安装：将 library/{library_id}/skill/ 复制到 skills/{name}/，无 DB 写入。
    
    【数据流】
    - 输入：仓库技能 ID (library_id), 安装目标 ("user" 运行层或特定 "project" 运行层)
    - 文件流：读取仓库目录 data/{user_uuid}/library/{library_id}/skill/ -> 复制到目标运行目录（例如 data/{user_uuid}/skills/{name}/ 或 data/{user_uuid}/{pid}/skills/{name}/）
    
    【调用链】
    - 客户端请求 -> APIRouter -> install_from_library()
    - 读取仓库信息 -> db.library.get_by_id() (db.py)
    - 校验/创建目标目录安全句柄 -> UserFile 或 ProjectFile (file.py)
    - 冲突检查 -> 确保目标路径下尚不存在同名目录
    - 物理复制 -> _copy_skill_dir()
    """
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


class WriteFileRequest(BaseModel):
    path: str = Field(..., min_length=1)
    content: str


@router.get("/skills/{library_id}/files")
def list_library_files(
    library_id: str,
    path: str = Query("."),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """列出仓库技能的文件。"""
    db = _resolve_db(db)
    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})

    library_fs = LibraryFile(library_id=library_id, user_uuid=current_user["uuid"], db_facade=db)
    try:
        entries = library_fs.search_dir(f"skill/{path}")
        return {"path": path, "entries": entries}
    except FileError as e:
        raise HTTPException(status_code=400, detail={"code": "FILE_ERROR", "message": str(e)})


@router.get("/skills/{library_id}/files/content")
def read_library_file(
    library_id: str,
    path: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """读取仓库技能的文件内容。"""
    db = _resolve_db(db)
    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})

    library_fs = LibraryFile(library_id=library_id, user_uuid=current_user["uuid"], db_facade=db)
    try:
        content = library_fs.read_file(f"skill/{path}")
        return {"path": path, "content": content}
    except FileError as e:
        raise HTTPException(status_code=400, detail={"code": "FILE_ERROR", "message": str(e)})


@router.put("/skills/{library_id}/files")
def write_library_file(
    library_id: str,
    payload: WriteFileRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """写入仓库技能的文件。"""
    db = _resolve_db(db)
    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})

    library_fs = LibraryFile(library_id=library_id, user_uuid=current_user["uuid"], db_facade=db)
    try:
        library_fs.create_file(f"skill/{payload.path}", payload.content)
        if payload.path == "SKILL.md":
            try:
                from backend.skill_parser import parse_skill_file
                fields = parse_skill_file(payload.content)
                db.library.update_meta(
                    library_id=library_id,
                    user_uuid=current_user["uuid"],
                    name=fields.name,
                    display_name=fields.display_name,
                    description=fields.description,
                    version=fields.version,
                )
            except Exception:
                pass
        return {"path": payload.path, "success": True}
    except FileError as e:
        raise HTTPException(status_code=400, detail={"code": "FILE_ERROR", "message": str(e)})


@router.put("/skills/{library_id}/meta", dependencies=[Depends(verify_nonce)])
def update_library_skill_meta(
    library_id: str,
    payload: UpdateLibrarySkillMetaRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """更新仓库技能的展示元数据。"""
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]

    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != user_uuid:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})

    db.library.update_meta(
        library_id=library_id,
        user_uuid=user_uuid,
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        readme_md=payload.readme_md,
        tags=payload.tags,
    )

    return db.library.get_by_id(library_id)


class BulkDeleteRequest(BaseModel):
    skill_ids: list[str] = Field(..., min_length=1, max_length=100)


@router.delete("/skills/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_skill(
    library_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """删除单条仓库技能及其本地文件。"""
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]

    record = db.library.get_by_id(library_id)
    if not record or record["user_uuid"] != user_uuid:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Library skill not found"})

    db.library.delete_for_user(library_id, user_uuid)

    # 清理本地文件
    try:
        local_path = record.get("local_path", "")
        if local_path:
            skill_dir = Path(local_path)
            if skill_dir.exists():
                shutil.rmtree(skill_dir, ignore_errors=True)
    except Exception:
        logger.warning("Failed to clean up local files for library skill %s", library_id)


@router.post("/skills/bulk-delete")
def bulk_delete_library_skills(
    payload: BulkDeleteRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """批量删除仓库技能，返回实际删除数量。"""
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]

    # 先查询需要删除的记录以清理文件
    records = []
    for sid in payload.skill_ids:
        record = db.library.get_by_id(sid)
        if record and record["user_uuid"] == user_uuid:
            records.append(record)

    deleted = db.library.delete_bulk_for_user(payload.skill_ids, user_uuid)

    # 清理本地文件
    for record in records:
        try:
            local_path = record.get("local_path", "")
            if local_path:
                skill_dir = Path(local_path)
                if skill_dir.exists():
                    shutil.rmtree(skill_dir, ignore_errors=True)
        except Exception:
            logger.warning("Failed to clean up local files for library skill %s", record["id"])

    return {"deleted": deleted}
