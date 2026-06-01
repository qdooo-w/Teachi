"""settings.py - 用户模型配置 API 路由

提供用户自定义模型配置的 CRUD 端点：
- 列出所有配置
- 创建新配置
- 获取当前激活配置
- 更新配置
- 激活/取消激活配置
- 删除配置
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.db import DatabaseFacade
from backend.db_dep import get_db

router = APIRouter(prefix="/settings", tags=["settings"])

# ─── 请求/响应模型 ──────────────────────────────────────────────────────────────

class ModelConfigItem(BaseModel):
    """模型配置输出项"""

    config_id: str
    config_name: str
    api_key: str  # 返回时脱敏，仅显示末4位
    base_url: str
    model_name: str
    user_instruction: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool
    supports_vision: bool
    created_at: float
    updated_at: float

class ModelConfigListResponse(BaseModel):
    """用户模型配置列表响应"""

    configs: list[ModelConfigItem]

class CreateModelConfigRequest(BaseModel):
    """创建模型配置请求"""

    config_name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    api_key: str = Field(default="", max_length=500, description="API Key")
    base_url: str = Field(default="", max_length=500, description="API Base URL")
    model_name: str = Field(default="", max_length=200, description="模型名称")
    user_instruction: str = Field(default="", max_length=2000, description="用户自定义指令")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int | None = Field(default=None, ge=1, le=128000, description="最大 token 数")
    is_active: bool = Field(default=False, description="是否激活")
    supports_vision: bool = Field(default=False, description="是否支持视觉")

class UpdateModelConfigRequest(BaseModel):
    """更新模型配置请求"""

    config_name: str | None = Field(default=None, min_length=1, max_length=100, description="配置名称")
    api_key: str | None = Field(default=None, max_length=500, description="API Key")
    base_url: str | None = Field(default=None, max_length=500, description="API Base URL")
    model_name: str | None = Field(default=None, max_length=200, description="模型名称")
    user_instruction: str | None = Field(default=None, max_length=2000, description="用户自定义指令")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int | None = Field(default=None, ge=1, le=128000, description="最大 token 数")
    supports_vision: bool | None = Field(default=None, description="是否支持视觉")

class ActiveConfigResponse(BaseModel):
    """当前激活配置响应"""

    config: ModelConfigItem | None = None

class TestConnectionRequest(BaseModel):
    """测试连接请求（保存前预检）"""

    api_key: str = Field(default="", max_length=500, description="API Key")
    base_url: str = Field(default="", max_length=500, description="API Base URL")
    model_name: str = Field(default="", max_length=200, description="模型名称")

class TestConnectionResponse(BaseModel):
    """测试连接响应"""

    success: bool
    message: str
    model: str | None = None

# ─── 辅助函数 ──────────────────────────────────────────────────────────────

def _mask_api_key(api_key: str) -> str:
    """对 API Key 脱敏：仅保留末4位，其余用 * 替代。

    短 Key（≤4位）保留末2位，让用户仍能区分不同配置。
    空 Key 返回空字串，前端可据此区分"已填写"和"未填写"。
    """
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "**" + api_key[-2:]
    return "*" * (len(api_key) - 4) + api_key[-4:]

def _row_to_item(row: dict) -> ModelConfigItem:
    """将数据库行转换为 API 输出模型，对 API Key 脱敏。"""
    return ModelConfigItem(
        config_id=row["config_id"],
        config_name=row["config_name"],
        api_key=_mask_api_key(row["api_key"]),
        base_url=row["base_url"],
        model_name=row["model_name"],
        user_instruction=row.get("user_instruction", ""),
        temperature=row["temperature"],
        max_tokens=row["max_tokens"],
        is_active=bool(row["is_active"]),
        supports_vision=bool(row.get("supports_vision", False)),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )

# ─── 路由 ──────────────────────────────────────────────────────────────

@router.get("/model-configs", response_model=ModelConfigListResponse)
def list_model_configs(
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ModelConfigListResponse:
    """列出当前用户的所有模型配置。"""
    user_uuid: str = current_user["uuid"]
    configs = db.model_configs.list_by_user(user_uuid)
    return ModelConfigListResponse(configs=[_row_to_item(c) for c in configs])

@router.post("/model-configs", response_model=ModelConfigItem, status_code=status.HTTP_201_CREATED)
def create_model_config(
    payload: CreateModelConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ModelConfigItem:
    """创建新的模型配置。"""
    user_uuid: str = current_user["uuid"]
    config = db.model_configs.create(
        user_uuid=user_uuid,
        config_name=payload.config_name,
        api_key=payload.api_key,
        base_url=payload.base_url,
        model_name=payload.model_name,
        user_instruction=payload.user_instruction,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_active=payload.is_active,
        supports_vision=payload.supports_vision,
    )
    return _row_to_item(config)

@router.get("/model-configs/active", response_model=ActiveConfigResponse)
def get_active_model_config(
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ActiveConfigResponse:
    """获取当前用户激活的模型配置。没有激活配置时返回 config=None。"""
    user_uuid: str = current_user["uuid"]
    config = db.model_configs.get_active_for_user(user_uuid)
    if config is None:
        return ActiveConfigResponse(config=None)
    return ActiveConfigResponse(config=_row_to_item(config))

@router.patch("/model-configs/{config_id}", response_model=ModelConfigItem)
def update_model_config(
    config_id: str,
    payload: UpdateModelConfigRequest,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ModelConfigItem:
    """更新模型配置。仅更新请求中提供的字段。"""
    user_uuid: str = current_user["uuid"]

    # 验证配置归属
    existing = db.model_configs.get_for_user(config_id, user_uuid)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Model config not found"},
        )

    updated = db.model_configs.update_for_user(
        config_id=config_id,
        user_uuid=user_uuid,
        config_name=payload.config_name,
        api_key=payload.api_key,
        base_url=payload.base_url,
        model_name=payload.model_name,
        user_instruction=payload.user_instruction,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        supports_vision=payload.supports_vision,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Model config not found"},
        )
    return _row_to_item(updated)

@router.post("/model-configs/{config_id}/activate", response_model=ModelConfigItem)
def activate_model_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> ModelConfigItem:
    """激活指定的模型配置（同时取消其他配置的激活状态）。"""
    user_uuid: str = current_user["uuid"]

    config = db.model_configs.set_active_for_user(config_id, user_uuid)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Model config not found"},
        )
    return _row_to_item(config)

@router.post("/model-configs/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_all_model_configs(
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """取消所有模型配置的激活状态，回到全局默认配置。"""
    user_uuid: str = current_user["uuid"]
    db.model_configs.deactivate_all_for_user(user_uuid)

@router.delete("/model-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """删除模型配置。"""
    user_uuid: str = current_user["uuid"]
    if not db.model_configs.delete_for_user(config_id, user_uuid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Model config not found"},
        )

@router.post("/model-configs/test-connection", response_model=TestConnectionResponse)
async def test_connection_with_params(
    payload: TestConnectionRequest,
    current_user: dict = Depends(get_current_user),
) -> TestConnectionResponse:
    """用原始参数测试 API 连通性（保存前预检）。

    传入的参数优先，未提供的字段回退到环境变量默认值。
    """
    from backend.config.model import test_connection

    result = await test_connection(
        api_key=payload.api_key or None,
        base_url=payload.base_url or None,
        model_name=payload.model_name or None,
    )
    return TestConnectionResponse(**result)

@router.post("/model-configs/{config_id}/test-connection", response_model=TestConnectionResponse)
async def test_connection_with_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> TestConnectionResponse:
    """用已保存的配置测试 API 连通性。"""
    user_uuid: str = current_user["uuid"]
    config = db.model_configs.get_for_user(config_id, user_uuid)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Model config not found"},
        )

    from backend.config.model import test_connection

    result = await test_connection(
        api_key=config["api_key"] or None,
        base_url=config["base_url"] or None,
        model_name=config["model_name"] or None,
    )
    return TestConnectionResponse(**result)

# ─── 账号设置 ──────────────────────────────────────────────────────────────

class UpdateUsernameRequest(BaseModel):
    """修改用户名请求"""
    username: str = Field(..., min_length=1, max_length=50, description="新用户名")

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    current_password: str = Field(..., min_length=6, max_length=128, description="当前密码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")

class AccountInfoResponse(BaseModel):
    """账号信息响应"""
    uuid: str
    username: str
    email: str
    created_at: float

@router.get("/account", response_model=AccountInfoResponse)
def get_account_info(
    current_user: dict = Depends(get_current_user),
) -> AccountInfoResponse:
    """获取当前用户账号信息。"""
    return AccountInfoResponse(
        uuid=current_user["uuid"],
        username=current_user["username"],
        email=current_user["email"],
        created_at=float(current_user["created_at"]),
    )

@router.patch("/account/username", response_model=AccountInfoResponse)
def update_username(
    payload: UpdateUsernameRequest,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> AccountInfoResponse:
    """修改用户名。"""
    user_uuid: str = current_user["uuid"]
    updated = db.users.update_username(user_uuid, payload.username)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "User not found"},
        )
    return AccountInfoResponse(
        uuid=updated["uuid"],
        username=updated["username"],
        email=updated["email"],
        created_at=float(updated["created_at"]),
    )

@router.post("/account/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """修改密码。需验证当前密码。成功后清除 refresh token，需重新登录。"""
    from backend.auth import verify_password, hash_password, _clear_refresh_cookie

    user_uuid: str = current_user["uuid"]
    stored_hash: str = current_user["password_hash"]

    if not verify_password(payload.current_password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PASSWORD", "message": "当前密码不正确"},
        )

    new_hash = hash_password(payload.new_password)
    db.users.update_password(user_uuid, new_hash)
    _clear_refresh_cookie(response)

# ─── 偏好设置 ──────────────────────────────────────────────────────────────

class PreferencesResponse(BaseModel):
    """用户偏好设置响应"""
    enter_mode: str = "enter"
    updated_at: float | None = None

class UpdatePreferencesRequest(BaseModel):
    """更新偏好设置请求"""
    enter_mode: str | None = Field(default=None, pattern="^(enter|ctrl_enter)$", description="发送键: enter 或 ctrl_enter")

@router.get("/preferences", response_model=PreferencesResponse)
def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> PreferencesResponse:
    """获取当前用户偏好设置。未设置过则返回默认值。"""
    user_uuid: str = current_user["uuid"]
    prefs = db.preferences.get_for_user(user_uuid)
    if prefs is None:
        return PreferencesResponse(enter_mode="enter", updated_at=None)
    return PreferencesResponse(
        enter_mode=prefs.get("enter_mode", "enter"),
        updated_at=float(prefs["updated_at"]),
    )

@router.patch("/preferences", response_model=PreferencesResponse)
def update_preferences(
    payload: UpdatePreferencesRequest,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
) -> PreferencesResponse:
    """更新用户偏好设置。"""
    user_uuid: str = current_user["uuid"]
    prefs = db.preferences.upsert_for_user(
        user_uuid,
        enter_mode=payload.enter_mode,
    )
    return PreferencesResponse(
        enter_mode=prefs.get("enter_mode", "enter"),
        updated_at=float(prefs["updated_at"]),
    )
