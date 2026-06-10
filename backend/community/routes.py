from __future__ import annotations

import logging
import uuid
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.config import (
    PAGE_DEFAULT_LIMIT,
    PAGE_MAX_LIMIT,
    SORT_DEFAULT,
    CommunitySkillSort,
)
from backend.community.utils import (
    resolve_db as _resolve_db,
    archive_root as _archive_root,
    resolve_archive_path as _resolve_archive_path,
    copy_skill_dir as _copy_skill_dir,
)
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from backend.file import FileBase, FileError, ProjectFile, UserFile, LibraryFile
from backend.skill_parser import validate_skill_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/community", tags=["community"])

class CommunitySkillSummary(BaseModel):
    id: str
    owner_uuid: str
    name: str
    display_name: str | None = None
    description: str
    likes: int
    downloads: int
    created_at: float
    updated_at: float
    version: str | None = None
    tags: str | None = None
    size_bytes: int | None = None

class CommunitySkillListResponse(BaseModel):
    skills: list[CommunitySkillSummary]
    total: int
    limit: int
    offset: int
    sort: CommunitySkillSort

class InstallSkillRequest(BaseModel):
    target: Literal["user", "project", "library"] = "user"
    pid: str | None = None
    version_id: str

class InstallResponse(BaseModel):
    name: str
    skill_id: str
    downloads: int

class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    parent_id: str | None = None
    reply_to_uuid: str | None = None

class ReportCreateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=100)
    detail: str = ""

def _to_summary(record: dict) -> CommunitySkillSummary:
    """
    将数据库中的技能记录字典转换为统一的社区技能摘要响应对象
    
    【数据流】
    - 输入：包含数据库字段的字典
    - 输出：结构化的 CommunitySkillSummary 实例
    """
    return CommunitySkillSummary(
        id=record["id"],
        owner_uuid=record["owner_uuid"],
        name=record["name"],
        display_name=record.get("display_name"),
        description=record["description"],
        likes=int(record.get("likes", 0)),
        downloads=int(record["downloads"]),
        created_at=float(record["created_at"]),
        updated_at=float(record["updated_at"]),
        version=record.get("version"),
        tags=record.get("tags"),
        size_bytes=record.get("size_bytes")
    )


def _install_target_fs(
    payload: InstallSkillRequest,
    user_uuid: str,
    db_facade: DatabaseFacade,
    library_id: str | None = None
) -> FileBase:
    """
    根据安装目标类型获取对应的文件系统管理器句柄
    
    【调用链】
    - 被 `install_community_skill` 接口调用，用于在执行文件复制前确认目标沙箱路径安全。
    - 返回：ProjectFile, LibraryFile 或 UserFile 的具体实例。
    """
    if payload.target == "project":
        if not payload.pid:
            raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "pid is required"})
        try:
            return ProjectFile(pid=payload.pid, user_uuid=user_uuid, db_facade=db_facade)
        except PermissionError:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Project not found"})
    elif payload.target == "library":
        if not library_id:
            raise HTTPException(status_code=500, detail={"code": "INTERNAL", "message": "library_id missing"})
        return LibraryFile(library_id=library_id, user_uuid=user_uuid, db_facade=db_facade)
    else:
        try:
            return UserFile(user_uuid=user_uuid, db_facade=db_facade)
        except PermissionError:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Access denied"})

@router.get("/leaderboard")
def get_community_leaderboard(
    limit: int = Query(10, ge=1, le=50),
    _user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """获取社区技能排行榜（按下载量排序）。"""
    db = _resolve_db(db)
    skills = db.community.list_skills(limit=limit, sort="popular")
    return {"skills": [_to_summary(s) for s in skills]}


@router.get("/skills", response_model=CommunitySkillListResponse)
def list_community_skills(
    keyword: str | None = Query(None, max_length=200),
    tag: list[str] = Query(default=[], max_length=50),
    limit: int = Query(PAGE_DEFAULT_LIMIT, ge=1, le=PAGE_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    sort: CommunitySkillSort = Query(SORT_DEFAULT),
    _user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    tags = tag if tag else None
    skills = db.community.list_skills(keyword=keyword, tags=tags, limit=limit, offset=offset, sort=sort)
    total = db.community.count_skills(keyword=keyword, tags=tags)
    return CommunitySkillListResponse(
        skills=[_to_summary(s) for s in skills],
        total=total,
        limit=limit,
        offset=offset,
        sort=sort,
    )

@router.get("/skills/{skill_id}")
def get_community_skill(
    skill_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    record = db.community.get_skill(skill_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Skill not found"})

    latest_version = db.community.get_latest_approved_version(skill_id)
    liked_by_me = db.community.is_liked_by_user(skill_id, current_user["uuid"])
    contributors = db.community.get_contributors(skill_id)

    res = _to_summary(record).model_dump()
    res["liked_by_me"] = liked_by_me
    res["contributors"] = contributors
    res["latest_version"] = latest_version
    return res

@router.get("/skills/{skill_id}/versions")
def list_skill_versions(
    skill_id: str,
    _user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    return db.community.list_versions(skill_id)

@router.post("/skills/{skill_id}/install", response_model=InstallResponse, dependencies=[Depends(verify_nonce)])
def install_community_skill(
    skill_id: str,
    payload: InstallSkillRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    安装社区技能：下载指定的已上架社区技能版本至本地或个人仓库
    
    【数据流】
    - 输入：社区技能 ID (skill_id), 目标安装层级 ("user"/"project"/"library"), 目标版本 ID (version_id)
    - 数据库流：如果是安装到仓库层 ("library")，在 user_library_skills 写入一条新记录同步。
    - 文件流：读取社区归档目录 archived_skill/{skill_id}/{version}/skill/ -> 复制到指定的目标运行路径或仓库路径。
    - 计数器流：更新 community_skills 及 community_skill_versions 中的下载量 (downloads + 1)。
    
    【调用链】
    - 客户端请求 -> APIRouter -> install_community_skill()
    - 获取社区技能记录 -> db.community.get_skill()
    - 获取指定版本记录 -> db.community.get_version()
    - 准备目标文件系统安全句柄 -> _install_target_fs() -> UserFile/ProjectFile/LibraryFile (file.py)
    - 物理文件复制 -> _copy_skill_dir()
    - 若目标为仓库，写入仓库记录 -> db.library.create() (db.py)
    - 更新下载量统计 -> db.community.increment_downloads() (db.py)
    """
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    
    skill_record = db.community.get_skill(skill_id)
    if not skill_record:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Skill not found"})
        
    version_record = db.community.get_version(payload.version_id)
    if not version_record or version_record["skill_id"] != skill_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Version not found"})

    name = skill_record["name"]

    # 安装到仓库时，复用 version_id 作为 library_id
    if payload.target == "library":
        library_id = payload.version_id
        # 检查是否已在仓库中（发布者发布时已创建，或其他用户已安装）
        existing = db.library.get_by_id(library_id)
        if existing:
            if existing["user_uuid"] == user_uuid:
                # 自己发布的技能，已在仓库中
                raise HTTPException(status_code=409, detail={"code": "ALREADY_IN_LIBRARY", "message": "该版本已在你的仓库中"})
            else:
                # 其他用户已安装过相同 version_id（理论上不应发生，因为 version_id 全局唯一）
                library_id = str(uuid.uuid4())
    else:
        library_id = None

    target_fs = _install_target_fs(payload, user_uuid, db, library_id)

    if payload.target == "library":
        skill_dir = target_fs.base_path / "skill"
    else:
        try:
            skill_dir = target_fs._safe_path(f"skills/{name}")
        except FileError:
            raise HTTPException(status_code=400, detail={"code": "INVALID_NAME", "message": "Invalid skill name"})

        if skill_dir.exists():
            raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": "Skill already exists locally"})

    try:
        archive_dir = _resolve_archive_path(version_record["archive_path"]) / "skill"
        if not archive_dir.is_dir():
            # Fallback to old format where content is directly in archive_path
            archive_dir = _resolve_archive_path(version_record["archive_path"])
        _copy_skill_dir(archive_dir, skill_dir)

        if payload.target == "library":
            # readme_md 从社区版本记录获取
            readme_content = version_record.get("readme_md", "")
            db.library.create(
                user_uuid=user_uuid,
                name=name,
                display_name=skill_record["display_name"],
                description=skill_record["description"],
                readme_md=readme_content,
                tags=version_record["tags"],
                version=version_record["version"],
                changelog=version_record["changelog"],
                source="community",
                community_skill_id=skill_id,  # 有值表示来自社区
                local_path=f"data/{user_uuid}/library/{library_id}",
                size_bytes=version_record["size_bytes"],
                skill_id=library_id
            )

    except FileError as e:
        raise HTTPException(status_code=400, detail={"code": "FILE_ERROR", "message": str(e)})

    db.community.increment_downloads(skill_id, version_id=payload.version_id)
    refreshed = db.community.get_skill(skill_id)
    return InstallResponse(name=name, skill_id=skill_id, downloads=int(refreshed["downloads"]))

@router.post("/skills/{skill_id}/like")
def toggle_skill_like(
    skill_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    liked = db.community.toggle_like(skill_id, current_user["uuid"])
    return {"liked": liked}

@router.get("/skills/{skill_id}/comments")
def list_comments(
    skill_id: str,
    parent_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    return db.community.list_comments(skill_id, parent_id, limit, offset, current_user_uuid=current_user["uuid"])

@router.post("/skills/{skill_id}/comments")
def create_comment(
    skill_id: str,
    payload: CommentCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    发表技能评论：支持一级评论和针对一级评论的回复（二级评论，即楼中楼）
    
    【数据流】
    - 输入：社区技能 ID (skill_id), 评论内容 (content), 父评论 ID (parent_id) 可选, 被回复用户 UUID (reply_to_uuid) 可选。
    - 验证：若是二级评论（parent_id 不为空），校验父评论是否存在且父评论层级本身必须是一级评论（最大层级嵌套为 2，即深度限制 <= 1）。
    - 数据库流：在 community_skill_comments 插入一条新记录。
    
    【调用链】
    - 客户端请求 -> APIRouter -> create_comment()
    - 写入数据库记录与嵌套校验 -> db.community.create_comment() (db.py::CommunitySkillsFacade)
    """
    db = _resolve_db(db)
    comment_id = str(uuid.uuid4())
    try:
        comment = db.community.create_comment(
            comment_id=comment_id,
            skill_id=skill_id,
            user_uuid=current_user["uuid"],
            content=payload.content,
            parent_id=payload.parent_id,
            reply_to_uuid=payload.reply_to_uuid
        )
        return comment
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "BAD_REQUEST", "message": str(e)})

@router.post("/comments/{comment_id}/like")
def toggle_comment_like(
    comment_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    liked = db.community.toggle_comment_like(comment_id, current_user["uuid"])
    return {"liked": liked}

@router.post("/comments/{comment_id}/report")
def report_comment(
    comment_id: str,
    payload: ReportCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    report_id = str(uuid.uuid4())
    report = db.community.create_report(
        report_id=report_id,
        comment_id=comment_id,
        reporter_uuid=current_user["uuid"],
        reason=payload.reason,
        detail=payload.detail
    )
    return report

@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community_skill(
    skill_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    record = db.community.get_skill(skill_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Skill not found"})
    if record["owner_uuid"] != current_user["uuid"]:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Only owner can delete"})
        
    db.community.delete_skill(skill_id)
    try:
        archive_dir = _resolve_archive_path(f"archived_skill/{skill_id}")
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
    except FileError:
        pass

@router.delete("/skills/{skill_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment_endpoint(
    skill_id: str,
    comment_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    删除评论：支持评论作者自行删除，以及全局系统管理员 (role == 'admin') 强行删除
    
    【数据流】
    - 输入：技能 ID (skill_id), 评论 ID (comment_id)
    - 权限判断：校验当前用户的 role 是否为 'admin' 以决定是否开启全局删除权限。
    - 数据库流：在 community_skill_comments 删除指定记录。
    
    【调用链】
    - 客户端请求 -> APIRouter -> delete_comment_endpoint()
    - 执行带权限控制的数据库删除 -> db.community.delete_comment() (db.py::CommunitySkillsFacade)
    """
    db = _resolve_db(db)
    is_admin = current_user.get("role") == "admin"
    deleted = db.community.delete_comment(comment_id, current_user["uuid"], is_admin=is_admin)
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Comment not found or not authorized"})


class AddContributorRequest(BaseModel):
    user_uuid: str


@router.get("/skills/{skill_id}/contributors")
def list_contributors(
    skill_id: str,
    _user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """获取技能贡献者列表。"""
    db = _resolve_db(db)
    return db.community.get_contributors(skill_id)


@router.post("/skills/{skill_id}/contributors")
def add_contributor(
    skill_id: str,
    payload: AddContributorRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """添加贡献者（仅技能管理员可操作）。"""
    db = _resolve_db(db)
    if not db.community.is_skill_admin(skill_id, current_user["uuid"]):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not an admin of this skill"})
    success = db.community.add_contributor(skill_id, payload.user_uuid)
    if not success:
        raise HTTPException(status_code=400, detail={"code": "BAD_REQUEST", "message": "Failed to add contributor"})
    return {"success": True}


@router.delete("/skills/{skill_id}/contributors/{user_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contributor(
    skill_id: str,
    user_uuid: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """移除贡献者（仅技能管理员可操作）。"""
    db = _resolve_db(db)
    if not db.community.is_skill_admin(skill_id, current_user["uuid"]):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not an admin of this skill"})
    success = db.community.remove_contributor(skill_id, user_uuid)
    if not success:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Contributor not found"})
