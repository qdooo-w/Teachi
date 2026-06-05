from __future__ import annotations

import logging
import shutil
import uuid
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.config import (
    BASE_DIR,
    PAGE_DEFAULT_LIMIT,
    PAGE_MAX_LIMIT,
    SORT_DEFAULT,
)
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from backend.file import FileBase, FileError, ProjectFile, UserFile, LibraryFile
from backend.skill_parser import validate_skill_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/community", tags=["community"])

def _resolve_db(db_param: Any) -> DatabaseFacade:
    if isinstance(db_param, DatabaseFacade):
        return db_param
    global_db = globals().get("db")
    if isinstance(global_db, DatabaseFacade):
        return global_db
    raise RuntimeError("DatabaseFacade not initialized in community module")

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
    sort: Literal["popular", "newest"]

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

def _archive_root() -> Path:
    root = (BASE_DIR / "archived_skill").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root

def _resolve_archive_path(archive_path: str) -> Path:
    root = _archive_root()
    target = (BASE_DIR / archive_path).resolve()
    if target != root and root not in target.parents:
        raise FileError("Archived skill path is outside archived_skill directory.")
    return target

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
    db_facade: DatabaseFacade,
    library_id: str | None = None
) -> FileBase:
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

@router.get("/skills", response_model=CommunitySkillListResponse)
def list_community_skills(
    keyword: str | None = Query(None, max_length=200),
    tag: str | None = Query(None, max_length=50),
    limit: int = Query(PAGE_DEFAULT_LIMIT, ge=1, le=PAGE_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    sort: Literal["popular", "newest"] = Query(SORT_DEFAULT),
    _user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    skills = db.community.list_skills(keyword=keyword, tag=tag, limit=limit, offset=offset, sort=sort)
    total = db.community.count_skills(keyword=keyword, tag=tag)
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
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    
    skill_record = db.community.get_skill(skill_id)
    if not skill_record:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Skill not found"})
        
    version_record = db.community.get_version(payload.version_id)
    if not version_record or version_record["skill_id"] != skill_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Version not found"})

    name = skill_record["name"]
    library_id = str(uuid.uuid4()) if payload.target == "library" else None
    
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
            # Extra library sync logic
            readme_path = skill_dir / "README.md"
            readme_content = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
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
                community_skill_id=skill_id,
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
    _user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    return db.community.list_comments(skill_id, parent_id, limit, offset)

@router.post("/skills/{skill_id}/comments")
def create_comment(
    skill_id: str,
    payload: CommentCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
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
    """删除评论：本人可删自己的评论，全局 admin 可强删任意评论。"""
    db = _resolve_db(db)
    is_admin = current_user.get("role") == "admin"
    deleted = db.community.delete_comment(comment_id, current_user["uuid"], is_admin=is_admin)
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Comment not found or not authorized"})
