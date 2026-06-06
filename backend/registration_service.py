# backend/registration_service.py

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, TypedDict
import os
import logging

from backend.config.seatable import SeaTableConfig
from backend.seatable_client import SeaTableClient, SeaTableAPIError, SeaTableNotFoundError

logger = logging.getLogger(__name__)


class VerificationResult(TypedDict):
    email: str
    expires_at: datetime
    identifier: str


class BaseRegistrationService(ABC):
    """注册激活与验证服务的抽象基类，用于解耦底层存储介质（如 SeaTable 或本地数据库）"""

    @abstractmethod
    async def verify_code(self, code: str) -> Optional[VerificationResult]:
        """验证激活码。如果有效则返回包含邮箱、过期时间和唯一标识的 VerificationResult，否则返回 None。"""
        pass

    @abstractmethod
    async def mark_registered(self, identifier: str) -> bool:
        """标记该激活信息对应的账号已注册完成。"""
        pass

    @abstractmethod
    async def mark_expired(self, identifier: str) -> bool:
        """标记该激活验证码已失效。"""
        pass

    @abstractmethod
    async def create_registration_request(self, email: str) -> bool:
        """为指定的邮箱地址创建注册申请记录并触发验证邮件发送。"""
        pass


class SeaTableRegistrationService(BaseRegistrationService):
    """基于 SeaTable 的注册验证服务实现"""

    def __init__(self):
        self.config = SeaTableConfig()
        self.client = SeaTableClient(self.config)

    async def verify_code(self, code: str) -> Optional[VerificationResult]:
        try:
            row = await self.client.find_row_by_verify_code(code)
        except SeaTableNotFoundError:
            return None
        except SeaTableAPIError as e:
            logger.error(f"SeaTable 验证码查询失败: {e}")
            raise RuntimeError("服务暂时不可用，请稍后再试") from e

        if not row:
            return None

        status_val = row.get("status")
        if status_val == "registered":
            raise ValueError("该邮箱已注册完成")
        if status_val not in ("pending", "email_sent"):
            raise ValueError("无效的验证码状态")

        expires_at_str = row.get("expires_at")
        if not expires_at_str:
            raise ValueError("验证码缺少过期时间")

        try:
            if expires_at_str.endswith("Z"):
                expires_at_str = expires_at_str[:-1] + "+00:00"
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise ValueError("失效时间格式错误") from e

        email = row.get("email")
        if not email:
            raise ValueError("注册记录中缺少邮箱信息")

        # 校验允许的邮箱后缀域名白名单
        allowed_domains_str = os.getenv("ALLOWED_EMAIL_DOMAINS", "").strip()
        if allowed_domains_str:
            allowed_domains = [d.strip() for d in allowed_domains_str.split(",") if d.strip()]
            if not any(email.endswith(f"@{domain}") for domain in allowed_domains):
                raise ValueError("该邮箱域名不被允许注册")

        return VerificationResult(
            email=email,
            expires_at=expires_at,
            identifier=row["row_id"]
        )

    async def mark_registered(self, identifier: str) -> bool:
        try:
            return await self.client.update_row_status(identifier, "registered")
        except SeaTableAPIError as e:
            logger.error(f"SeaTable 更新 registered 状态失败: {e}")
            return False

    async def mark_expired(self, identifier: str) -> bool:
        try:
            return await self.client.update_row_status(identifier, "expired")
        except SeaTableAPIError as e:
            logger.error(f"SeaTable 更新 expired 状态失败: {e}")
            return False

    async def create_registration_request(self, email: str) -> bool:
        try:
            return await self.client.add_registration_row(email)
        except SeaTableAPIError as e:
            logger.error(f"SeaTable 插入注册申请记录行失败: {e}")
            return False


# 实例化当前的注册服务（后期若更换为真正的邮箱系统，只需更改此处绑定的子类实现即可）
_registration_service: BaseRegistrationService = SeaTableRegistrationService()


def get_registration_service() -> BaseRegistrationService:
    """获取全局注册验证服务实例"""
    return _registration_service
