"""
community.py - 社区技能广场路由

5 个端点：
- GET    /community/skills            列表（关键字搜索 + 分页 + 排序）
- GET    /community/skills/{id}       详情（含正文）
- POST   /community/skills            发布
- POST   /community/skills/{id}/install   一键安装到我的私有 skills 目录
- DELETE /community/skills/{id}       删除（仅作者）

发布与安装走 nonce 防重放（与 loop.py 同语义）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, verify_nonce
from backend.config import DATABASE_PATH
from backend.db import DatabaseFacade
from backend.file import FileError, UserFile
from backend.skill_parser import (
    SKILL_MAX_BYTES,
    SkillParseError,
    parse_skill_file,
    utf8_byte_size,
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
    """详情：附带完整 SKILL.md。"""
    body_md: str


class CommunitySkillListResponse(BaseModel):
    skills: list[CommunitySkillSummary]
    total: int
    limit: int
    offset: int
    sort: Literal["popular", "newest"]


class PublishSkillRequest(BaseModel):
    """发布请求。后端只信任 body_md，name/description 从其中重新解析。"""
    body_md: str = Field(..., min_length=1)


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
    return CommunitySkillDetail(
        **_to_summary(record).model_dump(),
        body_md=record["body_md"],
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

    - 后端**重新解析** frontmatter，不信任前端字段
    - body_md UTF-8 字节数 ≤ SKILL_MAX_BYTES
    - 同一作者可重复发布同名 skill：每次都是独立条目
    """
    body_md = payload.body_md
    size_bytes = utf8_byte_size(body_md)
    if size_bytes > SKILL_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "SKILL_TOO_LARGE",
                "message": f"SKILL.md 不能超过 {SKILL_MAX_BYTES // 1024} KB（当前 {size_bytes} 字节）",
            },
        )

    try:
        fields = parse_skill_file(body_md)
    except SkillParseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "SKILL_PARSE_ERROR", "message": str(e)},
        )

    owner_uuid = current_user["uuid"]
    record = db.community.create(
        owner_uuid=owner_uuid,
        name=fields.name,
        description=fields.description,
        body_md=body_md,
        size_bytes=size_bytes,
        license=fields.license,
        compatibility=fields.compatibility,
    )
    logger.info("community_skill_published id=%s name=%s owner=%s", record["id"], fields.name, owner_uuid)
    return _to_detail(record)


@router.post(
    "/skills/{skill_id}/install",
    response_model=InstallResponse,
    dependencies=[Depends(verify_nonce)],
)
def install_community_skill(
    skill_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> InstallResponse:
    """把社区 skill 安装到当前用户的 data/{user_uuid}/skills/{name}/SKILL.md。

    - 本地已存在同名目录（不论是否含 SKILL.md）→ 409，由用户改名后重试
    - 安装成功后社区记录 downloads += 1
    """
    record = db.community.get_by_id(skill_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Community skill not found"},
        )

    user_uuid = current_user["uuid"]
    name = record["name"]
    body_md = record["body_md"]

    # 信任但验证：DB 中的 name 应已通过 publish 层校验，但仍兜底防御历史脏数据
    if validate_skill_name(name) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SKILL_NAME", "message": "Skill name in record is not safe"},
        )

    try:
        user_fs = UserFile(user_uuid=user_uuid, db_facade=db)
    except PermissionError:
        # 理论上 get_current_user 已校验，这里兜底
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access denied"},
        )

    # 目录冲突检测：直接看 skills/{name} 目录是否已存在
    target_rel = f"skills/{name}/SKILL.md"
    try:
        skill_dir = user_fs._safe_path(f"skills/{name}")
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
        user_fs.create_file(target_rel, body_md)
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
    if not db.community.delete_for_owner(skill_id, current_user["uuid"]):
        # 极端竞态：刚才存在，DELETE 之间被别人删了；按 404 处理更直观
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Community skill not found"},
        )
