from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.community.utils import resolve_db as _resolve_db
from backend.db import DatabaseFacade
from backend.db_dep import get_db

logger = logging.getLogger(__name__)

# 定义 Owner（技能管理员）和 Admin（系统管理员）路由
router_owner = APIRouter(prefix="/owner", tags=["owner"])
router_admin = APIRouter(prefix="/admin", tags=["admin"])


class ReviewActionRequest(BaseModel):
    """审核决策请求负载模型，包含审核备注信息"""
    note: str = ""

@router_owner.get("/reviews")
def list_owner_reviews(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """
    列出当前用户作为技能管理员 (Owner) 待审核的版本列表
    
    【数据流】
    - 输入：当前登录用户 UUID
    - 数据库流：关联 `community_skill_versions`、`community_skills` 和 `community_skill_admins` 专用管理员子表，
      过滤状态为 `PENDING_OWNER` 且该用户为管理员的技能版本记录。
    
    【调用链】
    - 客户端请求 -> APIRouter -> list_owner_reviews()
    - 通过 sqlite 直连或门面连接执行连表查询
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
    """
    Owner (技能管理员) 审批通过某个技能版本，将其状态流转为 PENDING_ADMIN，等待全局管理员审批。
    
    【数据流/验证逻辑】
    - 校验版本是否存在。
    - 校验当前用户是否为该技能的管理员 (`db.community.is_skill_admin()`)。
    - 校验版本状态是否为 `PENDING_OWNER`。
    - 数据库流：写入审核日志 `APPROVE_BY_OWNER`，版本状态跃迁至 `PENDING_ADMIN`。
    
    【调用链】
    - 客户端请求 -> APIRouter -> owner_approve() -> db.reviews.create() -> 原子化更新并记录日志。
    """
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
    """
    Owner (技能管理员) 拒绝某个技能版本，将其状态流转为 REJECTED。
    
    【数据流/验证逻辑】
    - 权限校验同 approve。
    - 数据库流：写入审核日志 `REJECT_BY_OWNER`，版本状态流转至 `REJECTED`。
    """
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
    列出所有等待全局系统管理员审批的技能版本 (PENDING_ADMIN)
    
    【数据流/权限验证】
    - 校验当前登录用户的全局角色必须为 `admin`。
    - 数据库流：查询状态为 `PENDING_ADMIN` 的全部版本记录。
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
    """
    全局系统管理员审批通过某个技能版本，将其状态流转为 APPROVED，上架社区
    
    【数据流/调用链】
    - 验证当前用户角色是否为 `admin`。
    - 验证该版本是否存在且当前状态为 `PENDING_ADMIN`。
    - 数据库流：
      1. 写入审核日志 `APPROVE_BY_ADMIN`。
      2. 状态原子流转至 `APPROVED`。
      3. 调用 `db.community.update_latest_version` 将社区主表的 `latest_version` 设置为此版本，发布生效。
    """
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
    """
    全局系统管理员拒绝某个技能版本，将其状态流转为 REJECTED
    
    【数据流/调用链】
    - 验证当前用户角色是否为 `admin`。
    - 验证版本状态。
    - 数据库流：写入日志 `REJECT_BY_ADMIN`，状态修改为 `REJECTED`。
    """
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


@router_admin.get("/community/reports")
def list_reports(
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """列出待处理的评论举报（仅系统管理员）。"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "System admin only"})

    db = _resolve_db(db)
    sql = """
        SELECT r.*, c.content as comment_content, u.username as reporter_name
        FROM community_comment_reports r
        JOIN community_skill_comments c ON r.comment_id = c.id
        JOIN users u ON r.reporter_uuid = u.uuid
    """
    params: list = []
    if status_filter:
        sql += " WHERE r.status = ?"
        params.append(status_filter)
    sql += " ORDER BY r.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with db.get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
