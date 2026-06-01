"""
data.py - 数据传输与查询路由模块

职责：
1. 提供资源查询相关 HTTP 端点
2. 提供工具注册表查询端点
3. 提供消息版本查询与切换端点
4. 提供基础健康检查端点（root/health）
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.config import (
    APP_NAME,
    SKILL_FILE_MAX_CHARS,
    SKILL_RESOURCE_DIRS,
    BASE_DIR,
)
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from backend.file import ProjectFile, UserFile, FileError, _TEXT_FILE_EXTENSIONS, validate_skill_storage_path
from backend.tool import get_registered_tool_names
from backend.transfer import router as transfer_router

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data"])
router.include_router(transfer_router)


@router.get("/")
def root() -> dict[str, str]:
    """服务根路由，用于快速确认服务在线。"""
    return {"service": APP_NAME, "status": "ok"}


@router.get("/health")
def health() -> dict[str, str]:
    """健康检查路由，用于探针与联调。"""
    return {"status": "healthy"}


class ProjectItem(BaseModel):
    """项目信息"""

    pid: str
    projectname: str
    timestamp: float
    created_at: float


class ProjectListResponse(BaseModel):
    """用户项目列表响应"""

    projects: list[ProjectItem]


class CreateProjectRequest(BaseModel):
    """创建项目请求"""

    projectname: str = Field(..., min_length=1, max_length=100, description="项目名称")


class UpdateProjectRequest(BaseModel):
    """重命名项目请求"""

    projectname: str = Field(..., min_length=1, max_length=100, description="项目新名称")


class SessionItem(BaseModel):
    """会话信息"""

    sid: str
    sessionname: str
    timestamp: float
    created_at: float


class SessionListResponse(BaseModel):
    """项目会话列表响应"""

    sessions: list[SessionItem]


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    sessionname: str = Field(..., min_length=1, max_length=100, description="会话名称")


class UpdateSessionRequest(BaseModel):
    """重命名会话请求"""

    sessionname: str = Field(..., min_length=1, max_length=100, description="会话新名称")


class MessageItem(BaseModel):
    """消息信息"""

    msg_id: str
    kind: str
    raw_json: str
    timestamp: float
    created_at: float
    anchor_msg_id: str | None = None
    version: int = 0


class MessageListResponse(BaseModel):
    """会话消息列表响应"""

    messages: list[MessageItem]


@router.get("/users/{user_id}/projects", response_model=ProjectListResponse)
def list_user_projects(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ProjectListResponse:
    """查询用户所拥有的项目"""
    jwt_user_uuid = current_user.get("uuid")
    if user_id != jwt_user_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access other user's projects"},
        )

    projects = db.projects.list_by_user(user_uuid=user_id)
    return ProjectListResponse(
        projects=[
            ProjectItem(
                pid=p["pid"],
                projectname=p["projectname"],
                timestamp=float(p["timestamp"]),
                created_at=float(p["created_at"]),
            )
            for p in projects
        ]
    )


@router.post(
    "/users/{user_id}/projects",
    response_model=ProjectItem,
    status_code=status.HTTP_201_CREATED,
)
def create_user_project(
    user_id: str,
    payload: CreateProjectRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ProjectItem:
    """为用户创建新项目。"""
    jwt_user_uuid = current_user.get("uuid")
    if user_id != jwt_user_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot create project for other user"},
        )
    project = db.projects.create(
        projectname=payload.projectname,
        user_uuid=user_id,
    )
    return ProjectItem(
        pid=project["pid"],
        projectname=project["projectname"],
        timestamp=float(project["timestamp"]),
        created_at=float(project["created_at"]),
    )


@router.patch("/projects/{pid}", response_model=ProjectItem)
def rename_project(
    pid: str,
    payload: UpdateProjectRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ProjectItem:
    """重命名项目。项目不存在或不属于当前用户返回 404。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    project = db.projects.update_name_for_user(
        pid=pid,
        user_uuid=user_uuid,
        projectname=payload.projectname,
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )
    return ProjectItem(
        pid=project["pid"],
        projectname=project["projectname"],
        timestamp=float(project["timestamp"]),
        created_at=float(project["created_at"]),
    )


@router.delete("/projects/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    pid: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除项目。外键 ON DELETE CASCADE 会级联删除该项目下所有会话与消息。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    if not db.projects.delete_for_user(pid=pid, user_uuid=user_uuid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )

    # 递归删除物理目录：data/{user_uuid}/{pid}/
    if user_uuid and pid:
        project_dir = (BASE_DIR / "data" / user_uuid / pid).resolve()
        data_dir = (BASE_DIR / "data").resolve()
        if data_dir in project_dir.parents:
            if project_dir.exists() and project_dir.is_dir():
                shutil.rmtree(project_dir)


@router.get("/projects/{pid}/sessions", response_model=SessionListResponse)
def list_project_sessions(
    pid: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> SessionListResponse:
    """查询项目下的所有会话"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    project = db.projects.get_for_user(pid=pid, user_uuid=user_uuid)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )

    sessions = db.sessions.list_by_project(pid=pid)
    return SessionListResponse(
        sessions=[
            SessionItem(
                sid=s["sid"],
                sessionname=s["sessionname"],
                timestamp=float(s["timestamp"]),
                created_at=float(s["created_at"]),
            )
            for s in sessions
        ]
    )


@router.post(
    "/projects/{pid}/sessions",
    response_model=SessionItem,
    status_code=status.HTTP_201_CREATED,
)
def create_project_session(
    pid: str,
    payload: CreateSessionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> SessionItem:
    """在项目下创建新会话。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    project = db.projects.get_for_user(pid=pid, user_uuid=user_uuid)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )

    session = db.sessions.create(
        pid=pid,
        sessionname=payload.sessionname,
    )
    return SessionItem(
        sid=session["sid"],
        sessionname=session["sessionname"],
        timestamp=float(session["timestamp"]),
        created_at=float(session["created_at"]),
    )


@router.patch("/sessions/{sid}", response_model=SessionItem)
def rename_session(
    sid: str,
    payload: UpdateSessionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> SessionItem:
    """重命名会话。会话不存在或不属于当前用户返回 404。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    session = db.sessions.update_name_for_user(
        sid=sid,
        user_uuid=user_uuid,
        sessionname=payload.sessionname,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )
    return SessionItem(
        sid=session["sid"],
        sessionname=session["sessionname"],
        timestamp=float(session["timestamp"]),
        created_at=float(session["created_at"]),
    )


@router.delete("/sessions/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    sid: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除会话。外键 ON DELETE CASCADE 会级联删除该会话下所有消息。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    pid = session["pid"]

    if not db.sessions.delete_for_user(sid=sid, user_uuid=user_uuid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    # 递归删除物理目录：data/{user_uuid}/{pid}/{sid}/
    if user_uuid and pid and sid:
        session_dir = (BASE_DIR / "data" / user_uuid / pid / sid).resolve()
        data_dir = (BASE_DIR / "data").resolve()
        if data_dir in session_dir.parents:
            if session_dir.exists() and session_dir.is_dir():
                shutil.rmtree(session_dir)


@router.get("/sessions/{sid}/messages", response_model=MessageListResponse)
def list_session_messages(
    sid: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> MessageListResponse:
    """查询会话的所有消息"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    messages = db.messages.list_by_session_for_user(sid=sid, user_uuid=user_uuid)
    return MessageListResponse(
        messages=[
            MessageItem(
                msg_id=m["msg_id"],
                kind=m["kind"],
                raw_json=m["raw_json"],
                timestamp=float(m["timestamp"]),
                created_at=float(m["created_at"]),
                anchor_msg_id=m.get("anchor_msg_id"),
                version=int(m.get("version", 0) or 0),
            )
            for m in messages
        ]
    )


class ToolRegistryResponse(BaseModel):
    """工具注册表查询响应"""

    tools: list[str]
    global_allowed_tools: list[str]


@router.get("/tools/registry", response_model=ToolRegistryResponse)
def list_tool_registry() -> ToolRegistryResponse:
    """查询工具注册表。"""
    return ToolRegistryResponse(
        tools=sorted(get_registered_tool_names()),
        global_allowed_tools=sorted(get_registered_tool_names()),
    )


class MessageVersionItem(BaseModel):
    """消息版本项"""

    msg_id: str
    kind: str
    raw_json: str
    anchor_msg_id: str | None = None
    version: int
    timestamp: float
    created_at: float


class MessageVersionsResponse(BaseModel):
    """消息版本列表响应"""

    versions: list[MessageVersionItem]


@router.get("/messages/{msg_id}/versions", response_model=MessageVersionsResponse)
def get_message_versions(
    msg_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> MessageVersionsResponse:
    """查询某个回合 anchor 下的所有版本消息（含活跃版 version=0 与历史版 version>0）。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    versions = db.messages.list_versions(
        anchor_msg_id=msg_id,
        user_uuid=user_uuid,
    )
    return MessageVersionsResponse(
        versions=[
            MessageVersionItem(
                msg_id=v["msg_id"],
                kind=v["kind"],
                raw_json=v["raw_json"],
                anchor_msg_id=v.get("anchor_msg_id"),
                version=int(v["version"]),
                timestamp=float(v["timestamp"]),
                created_at=float(v["created_at"]),
            )
            for v in versions
        ]
    )


class SwitchVersionRequest(BaseModel):
    """切换版本请求"""

    target_version_msg_id: str = Field(..., description="要切换到活跃位（version=0）的版本消息 ID")


class SwitchVersionResponse(BaseModel):
    """切换版本响应"""

    success: bool
    switched_msg_id: str


@router.post("/messages/{msg_id}/switch-version", response_model=SwitchVersionResponse)
def switch_to_message_version(
    msg_id: str,
    payload: SwitchVersionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> SwitchVersionResponse:
    """切换到指定版本：把 target_version_msg_id 所在版本与 version=0 整组对调。

    整组 swap 保证同一回合内 user / tool_call / tool_result / assistant 的版本不会错位。
    """
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    success = db.messages.swap_version_group(
        msg_id=payload.target_version_msg_id,
        user_uuid=user_uuid,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SWITCH_FAILED", "message": "Failed to switch version"},
        )

    return SwitchVersionResponse(
        success=True,
        switched_msg_id=payload.target_version_msg_id,
    )


@router.delete("/messages/{anchor_msg_id}/turn", status_code=status.HTTP_204_NO_CONTENT)
def delete_active_turn(
    anchor_msg_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除该回合当前活跃版本（version=0）的整组消息。

    范围：anchor_msg_id 指向的回合下，所有 version=0 的消息（user 自身 +
    tool_call / tool_result / assistant / agent_response）一并物理删除。
    历史版本（version>=1）保留，可通过版本切换功能恢复。
    """
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    affected = db.messages.delete_active_turn(
        anchor_msg_id=anchor_msg_id,
        user_uuid=user_uuid,
    )
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Active turn not found"},
        )


# ── 附件 API 模型 ───────────────────────────────────────────────────────────────

class AttachmentUploadResponse(BaseModel):
    """附件上传成功响应"""

    attachment_id: str
    original_filename: str
    mime_type: str
    created_at: float


class AttachmentListItem(BaseModel):
    """附件列表项"""

    attachment_id: str
    anchor_msg_id: str | None = None
    original_filename: str
    mime_type: str
    has_description: bool
    created_at: float


class AttachmentListResponse(BaseModel):
    """附件列表响应"""

    attachments: list[AttachmentListItem]


@router.post(
    "/sessions/{sid}/attachments",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    sid: str,
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> AttachmentUploadResponse:
    """上传附件。限制大小 10MB，仅支持 JPEG/PNG/WebP/GIF，对魔术字节进行校验。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    # 校验会话是否存在且属于该用户
    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    pid = session["pid"]

    # 校验文件大小 (最大 10MB)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_TOO_LARGE", "message": "File size exceeds 10MB limit"},
        )

    # 校验 MIME_TYPE
    mime_type = file.content_type
    allowed_mimes = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if mime_type not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_MIME_TYPE", "message": f"MIME type {mime_type} is not allowed"},
        )

    # 魔术字节校验
    magic_bytes_map = {
        "image/jpeg": b"\xff\xd8\xff",
        "image/png": b"\x89PNG",
        "image/webp": b"RIFF",
        "image/gif": b"GIF",
    }
    expected_magic = magic_bytes_map[mime_type]
    if not content.startswith(expected_magic):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILE_CONTENT", "message": "Magic bytes validation failed"},
        )

    # 物理文件存储路径：data/{user_uuid}/{pid}/{sid}/attachments/{attachment_id}{ext}
    attachment_id = str(uuid.uuid4())
    ext = Path(file.filename or "").suffix.lower()
    if not ext:
        fallback = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif"
        }
        ext = fallback.get(mime_type, "")

    rel_path = f"data/{user_uuid}/{pid}/{sid}/attachments/{attachment_id}{ext}"
    full_path = BASE_DIR / rel_path

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "FILE_WRITE_ERROR", "message": f"Failed to save file physically: {e}"},
        )

    # 写入数据库记录
    record = db.attachments.create(
        sid=sid,
        user_uuid=user_uuid,
        original_filename=file.filename or "file",
        file_path=rel_path,
        mime_type=mime_type,
        attachment_id=attachment_id,
    )

    return AttachmentUploadResponse(
        attachment_id=record["attachment_id"],
        original_filename=record["original_filename"],
        mime_type=record["mime_type"],
        created_at=record["created_at"],
    )


@router.get(
    "/sessions/{sid}/attachments",
    response_model=AttachmentListResponse,
)
def list_session_attachments(
    sid: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> AttachmentListResponse:
    """查询会话的所有附件"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    # 校验会话是否存在且属于该用户
    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    attachments = db.attachments.list_by_session(sid=sid, user_uuid=user_uuid)

    return AttachmentListResponse(
        attachments=[
            AttachmentListItem(
                attachment_id=item["attachment_id"],
                anchor_msg_id=item["anchor_msg_id"],
                original_filename=item["original_filename"],
                mime_type=item["mime_type"],
                has_description=bool(item.get("description")),
                created_at=item["created_at"],
            )
            for item in attachments
        ]
    )


@router.delete(
    "/sessions/{sid}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session_attachment(
    sid: str,
    attachment_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除指定的会话附件。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )

    # 校验会话是否存在且属于该用户
    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    # 校验附件是否存在，属于该用户且属于指定 session
    attachment = db.attachments.get_for_user(attachment_id, user_uuid)
    if attachment is None or attachment["sid"] != sid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Attachment not found"},
        )

    # 从数据库删除
    db.attachments.delete(attachment_id, user_uuid)

    # 清理物理文件
    file_path_str = attachment["file_path"]
    if file_path_str:
        full_path = BASE_DIR / file_path_str
        if full_path.exists():
            try:
                full_path.unlink()
            except Exception as e:
                # Log the error but don't crash
                logger.warning("Failed to delete physical file %s: %s", full_path, e)


# ── 文件 API 模型 ───────────────────────────────────────────────────────────────

class FileListEntry(BaseModel):
    """目录条目信息"""

    name: str
    is_dir: bool
    rel_path: str
    size: int
    updated_at: float


class FileListResponse(BaseModel):
    """目录列表响应"""

    path: str
    entries: list[FileListEntry]


class FileContentResponse(BaseModel):
    """文件内容响应"""

    path: str
    content: str
    size: int
    updated_at: float


class WriteFileRequest(BaseModel):
    """写文件请求"""

    path: str
    content: str = Field(..., max_length=SKILL_FILE_MAX_CHARS)


class CreateDirectoryRequest(BaseModel):
    """创建目录请求"""

    path: str = Field(..., min_length=1, max_length=512)

def _check_text_extension(path: str) -> None:
    """检查文件扩展名是否在文本白名单内，否则抛 415。"""
    ext = Path(path).suffix.lower()
    if ext not in _TEXT_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": "UNSUPPORTED_FILE_TYPE", "message": f"File type {ext!r} is not supported"},
        )


def _validate_file_write_path(path: str) -> None:
    _check_text_extension(path)
    try:
        validate_skill_storage_path(path)
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        ) from e


def _validate_file_read_path(path: str) -> None:
    _check_text_extension(path)
    try:
        validate_skill_storage_path(path)
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        ) from e


def _validate_file_delete_path(path: str) -> None:
    try:
        validate_skill_storage_path(path, allow_skill_dir=True)
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        ) from e


def _validate_file_directory_path(path: str) -> None:
    try:
        validate_skill_storage_path(path)
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        ) from e
    parts = Path(path).parts
    if len(parts) != 3 or parts[0] != "skills" or parts[2] not in SKILL_RESOURCE_DIRS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "FILE_ERROR",
                "message": "Skill folders can only be skills/<name>/references, skills/<name>/assets, skills/<name>/examples or skills/<name>/templates",
            },
        )


# ── 用户级文件路由 ──────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/files", response_model=FileListResponse)
def list_user_files(
    user_id: str,
    path: str = ".",
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> FileListResponse:
    """列出用户文件目录。"""
    if user_id != current_user.get("uuid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access other user's files"},
        )
    try:
        fs = UserFile(user_uuid=user_id, db_facade=db)
        entries = fs.search_dir(path) if (fs._safe_path(path)).is_dir() else []
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
    return FileListResponse(
        path=path,
        entries=[FileListEntry(**e) for e in entries],
    )


@router.get("/users/{user_id}/files/content", response_model=FileContentResponse)
def read_user_file(
    user_id: str,
    path: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> FileContentResponse:
    """读取用户文件内容。"""
    if user_id != current_user.get("uuid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access other user's files"},
        )
    _validate_file_read_path(path)
    try:
        fs = UserFile(user_uuid=user_id, db_facade=db)
        safe = fs._safe_path(path)
        if not safe.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "File not found"},
            )
        content = fs.read_file(path)
        stat = safe.stat()
        return FileContentResponse(path=path, content=content, size=stat.st_size, updated_at=stat.st_mtime)
    except HTTPException:
        raise
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


@router.put("/users/{user_id}/files", response_model=FileContentResponse)
def write_user_file(
    user_id: str,
    payload: WriteFileRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> FileContentResponse:
    """写入或覆盖用户文件。"""
    if user_id != current_user.get("uuid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access other user's files"},
        )
    _validate_file_write_path(payload.path)
    try:
        fs = UserFile(user_uuid=user_id, db_facade=db)
        fs.create_file(payload.path, payload.content)
        safe = fs._safe_path(payload.path)
        stat = safe.stat()
        return FileContentResponse(
            path=payload.path, content=payload.content, size=stat.st_size, updated_at=stat.st_mtime
        )
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


@router.post("/users/{user_id}/files/directories", status_code=status.HTTP_204_NO_CONTENT)
def create_user_directory(
    user_id: str,
    payload: CreateDirectoryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """创建用户文件目录。当前仅允许 materialize skill 规范目录。"""
    if user_id != current_user.get("uuid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access other user's files"},
        )
    try:
        _validate_file_directory_path(payload.path)
        fs = UserFile(user_uuid=user_id, db_facade=db)
        fs.create_dir(payload.path)
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


@router.delete("/users/{user_id}/files", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_file(
    user_id: str,
    path: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除用户文件或目录。"""
    if user_id != current_user.get("uuid"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot access other user's files"},
        )
    _validate_file_delete_path(path)
    try:
        fs = UserFile(user_uuid=user_id, db_facade=db)
        safe = fs._safe_path(path)
        if not safe.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Path not found"},
            )
        if safe.is_dir():
            fs.delete_dir(path)
        else:
            fs.delete_file(path)
    except HTTPException:
        raise
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


# ── 项目级文件路由 ──────────────────────────────────────────────────────────────

@router.get("/projects/{pid}/files", response_model=FileListResponse)
def list_project_files(
    pid: str,
    path: str = ".",
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> FileListResponse:
    """列出项目文件目录。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )
    try:
        fs = ProjectFile(pid=pid, user_uuid=user_uuid, db_facade=db)
        entries = fs.search_dir(path) if (fs._safe_path(path)).is_dir() else []
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )
    return FileListResponse(
        path=path,
        entries=[FileListEntry(**e) for e in entries],
    )


@router.get("/projects/{pid}/files/content", response_model=FileContentResponse)
def read_project_file(
    pid: str,
    path: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> FileContentResponse:
    """读取项目文件内容。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )
    _validate_file_read_path(path)
    try:
        fs = ProjectFile(pid=pid, user_uuid=user_uuid, db_facade=db)
        safe = fs._safe_path(path)
        if not safe.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "File not found"},
            )
        content = fs.read_file(path)
        stat = safe.stat()
        return FileContentResponse(path=path, content=content, size=stat.st_size, updated_at=stat.st_mtime)
    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )


@router.put("/projects/{pid}/files", response_model=FileContentResponse)
def write_project_file(
    pid: str,
    payload: WriteFileRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> FileContentResponse:
    """写入或覆盖项目文件。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )
    _validate_file_write_path(payload.path)
    try:
        fs = ProjectFile(pid=pid, user_uuid=user_uuid, db_facade=db)
        fs.create_file(payload.path, payload.content)
        safe = fs._safe_path(payload.path)
        stat = safe.stat()
        return FileContentResponse(
            path=payload.path, content=payload.content, size=stat.st_size, updated_at=stat.st_mtime
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )


@router.post("/projects/{pid}/files/directories", status_code=status.HTTP_204_NO_CONTENT)
def create_project_directory(
    pid: str,
    payload: CreateDirectoryRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """创建项目文件目录。当前仅允许 materialize skill 规范目录。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )
    try:
        _validate_file_directory_path(payload.path)
        fs = ProjectFile(pid=pid, user_uuid=user_uuid, db_facade=db)
        fs.create_dir(payload.path)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )


@router.delete("/projects/{pid}/files", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_file(
    pid: str,
    path: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除项目文件或目录。"""
    user_uuid = current_user.get("uuid")
    if not isinstance(user_uuid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_TOKEN_INVALID", "message": "Invalid token"},
        )
    _validate_file_delete_path(path)
    try:
        fs = ProjectFile(pid=pid, user_uuid=user_uuid, db_facade=db)
        safe = fs._safe_path(path)
        if not safe.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Path not found"},
            )
        if safe.is_dir():
            fs.delete_dir(path)
        else:
            fs.delete_file(path)
    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Project not found"},
        )
    except FileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_ERROR", "message": str(e)},
        )
