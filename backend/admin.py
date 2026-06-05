from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.db import DatabaseFacade
from backend.db_dep import get_db

logger = logging.getLogger(__name__)

router_owner = APIRouter(prefix="/owner", tags=["owner"])
router_admin = APIRouter(prefix="/admin", tags=["admin"])

def _resolve_db(db_param: Any) -> DatabaseFacade:
    if isinstance(db_param, DatabaseFacade):
        return db_param
    global_db = globals().get("db")
    if isinstance(global_db, DatabaseFacade):
        return global_db
    raise RuntimeError("DatabaseFacade not initialized in admin module")

class ReviewActionRequest(BaseModel):
    note: str = ""

@router_owner.get("/reviews")
def list_owner_reviews(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    List versions waiting for OWNER approval (PENDING_OWNER).
    Only includes skills where current user is in community_skill_admins.
    """
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]

    sql = """
        SELECT v.*, s.name AS skill_name
        FROM community_skill_versions v
        JOIN community_skills s ON v.skill_id = s.id
        JOIN community_skill_admins a ON a.skill_id = s.id AND a.user_uuid = ?
        WHERE v.status = 'PENDING_OWNER'
    """
    with db.get_connection() as conn:
        rows = conn.execute(sql, (user_uuid,)).fetchall()
    return [dict(r) for r in rows]

@router_owner.post("/reviews/{version_id}/approve")
def owner_approve(
    version_id: str,
    payload: ReviewActionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    version = db.community.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Version not found"})
        
    if not db.community.is_skill_admin(version["skill_id"], user_uuid):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not an owner/admin of this skill"})
        
    if version["status"] != "PENDING_OWNER":
        raise HTTPException(status_code=400, detail={"code": "BAD_STATUS", "message": "Version is not in PENDING_OWNER state"})
        
    log = db.reviews.create(
        version_id=version_id,
        reviewer_uuid=user_uuid,
        action="APPROVE_BY_OWNER",
        from_status="PENDING_OWNER",
        to_status="PENDING_ADMIN",
        note=payload.note
    )
    return log

@router_owner.post("/reviews/{version_id}/reject")
def owner_reject(
    version_id: str,
    payload: ReviewActionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    version = db.community.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Version not found"})
        
    if not db.community.is_skill_admin(version["skill_id"], user_uuid):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Not an owner/admin of this skill"})
        
    if version["status"] != "PENDING_OWNER":
        raise HTTPException(status_code=400, detail={"code": "BAD_STATUS", "message": "Version is not in PENDING_OWNER state"})
        
    log = db.reviews.create(
        version_id=version_id,
        reviewer_uuid=user_uuid,
        action="REJECT_BY_OWNER",
        from_status="PENDING_OWNER",
        to_status="REJECTED",
        note=payload.note
    )
    return log


@router_admin.get("/reviews")
def list_admin_reviews(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    List versions waiting for ADMIN approval (PENDING_ADMIN).
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "System admin only"})
        
    db = _resolve_db(db)
    sql = """
        SELECT v.*, s.name as skill_name 
        FROM community_skill_versions v
        JOIN community_skills s ON v.skill_id = s.id
        WHERE v.status = 'PENDING_ADMIN'
    """
    with db.get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]

@router_admin.post("/reviews/{version_id}/approve")
def admin_approve(
    version_id: str,
    payload: ReviewActionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "System admin only"})
        
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    version = db.community.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Version not found"})
        
    if version["status"] != "PENDING_ADMIN":
        raise HTTPException(status_code=400, detail={"code": "BAD_STATUS", "message": "Version is not in PENDING_ADMIN state"})
        
    log = db.reviews.create(
        version_id=version_id,
        reviewer_uuid=user_uuid,
        action="APPROVE_BY_ADMIN",
        from_status="PENDING_ADMIN",
        to_status="APPROVED",
        note=payload.note
    )
    
    db.community.update_latest_version(version["skill_id"], version["version"])
    
    return log

@router_admin.post("/reviews/{version_id}/reject")
def admin_reject(
    version_id: str,
    payload: ReviewActionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "System admin only"})
        
    db = _resolve_db(db)
    user_uuid = current_user["uuid"]
    version = db.community.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Version not found"})
        
    if version["status"] != "PENDING_ADMIN":
        raise HTTPException(status_code=400, detail={"code": "BAD_STATUS", "message": "Version is not in PENDING_ADMIN state"})
        
    log = db.reviews.create(
        version_id=version_id,
        reviewer_uuid=user_uuid,
        action="REJECT_BY_ADMIN",
        from_status="PENDING_ADMIN",
        to_status="REJECTED",
        note=payload.note
    )
    return log
