# backend/seatable_client.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import httpx

from backend.config.seatable import SeaTableConfig

logger = logging.getLogger(__name__)


class SeaTableAPIError(Exception):
    pass


class SeaTableAuthError(SeaTableAPIError):
    pass


class SeaTableNotFoundError(SeaTableAPIError):
    pass


class SeaTableClient:
    def __init__(self, config: SeaTableConfig):
        self.config = config
        self._http = httpx.AsyncClient(timeout=30.0)
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._dtable_server: Optional[str] = None

    async def close(self):
        await self._http.aclose()

    async def _ensure_access_token(self) -> None:
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(hours=1):
                return
        await self._refresh_access_token()

    async def _refresh_access_token(self) -> None:
        url = f"{self.config.server_url}/api/v2.1/dtable/app-access-token/"
        headers = {
            "Authorization": f"Bearer {self.config.api_token}",
            "Accept": "application/json",
        }
        try:
            resp = await self._http.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise SeaTableAuthError("API Token 无效或被吊销")
            raise SeaTableAPIError(f"获取 access_token 失败: {e}")
        except Exception as e:
            raise SeaTableAPIError(f"请求 access_token 时发生错误: {e}")

        self._access_token = data.get("access_token")
        self._dtable_server = data.get("dtable_server", self.config.server_url)
        if not self._access_token:
            raise SeaTableAPIError("响应中缺少 access_token")
        self._token_expires_at = datetime.now() + timedelta(days=2, hours=23)
        logger.info(f"access_token 刷新成功，有效期至 {self._token_expires_at}")

    async def _request(self, method: str, url: str, retry_auth: bool = True, **kwargs) -> Dict[str, Any]:
        await self._ensure_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        headers["Accept"] = "application/json"
        try:
            resp = await self._http.request(method, url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 and retry_auth:
                logger.warning("access_token 可能已过期，尝试刷新后重试")
                await self._refresh_access_token()
                return await self._request(method, url, retry_auth=False, **kwargs)
            if e.response.status_code == 404:
                raise SeaTableNotFoundError("请求的资源不存在")
            raise SeaTableAPIError(f"API 请求失败: {e}. 响应内容: {e.response.text}")
        except httpx.TimeoutException:
            raise SeaTableAPIError("请求超时")
        except Exception as e:
            raise SeaTableAPIError(f"请求过程中发生错误: {e}")

    async def find_row_by_verify_code(self, code: str) -> Optional[Dict[str, Any]]:
        # 确保 access_token 和 dtable_server 已获取
        await self._ensure_access_token()
        
        sql = (
            f"SELECT `_id`, `{self.config.column_email}`, "
            f"`{self.config.column_status}`, `{self.config.column_expires}` "
            f"FROM `{self.config.table_name}` "
            f"WHERE `{self.config.column_code}` = ?"
        )
        base = self._dtable_server.rstrip('/')
        url = f"{base}/api/v2/dtables/{self.config.base_uuid}/sql/"
        payload = {"sql": sql, "parameters": [code], "convert_keys": True}
        try:
            resp_data = await self._request("POST", url, json=payload)
            rows = resp_data.get("results", [])
            if not rows:
                return None
            row = rows[0]
            return {
                "row_id": row.get("_id"),
                "email": row.get(self.config.column_email),
                "status": row.get(self.config.column_status),
                "expires_at": row.get(self.config.column_expires),
            }
        except SeaTableNotFoundError:
            logger.warning(f"查询验证码时资源不存在: {code}")
            return None
        except SeaTableAPIError:
            raise
 
    async def update_row_status(self, row_id: str, new_status: str) -> bool:
        # 确保 access_token 和 dtable_server 已获取
        await self._ensure_access_token()
        
        base = self._dtable_server.rstrip('/')
        url = f"{base}/api/v2/dtables/{self.config.base_uuid}/rows/"
        payload = {
            "table_name": self.config.table_name,
            "updates": [{"row_id": row_id, "row": {self.config.column_status: new_status}}]
        }
        try:
            await self._request("PUT", url, json=payload)
            logger.info(f"行 {row_id} 状态已更新为 {new_status}")
            return True
        except SeaTableAPIError:
            raise

    async def add_registration_row(self, email: str) -> bool:
        # 确保 access_token 和 dtable_server 已获取
        await self._ensure_access_token()
        
        base = self._dtable_server.rstrip('/')
        url = f"{base}/api/v2/dtables/{self.config.base_uuid}/rows/"
        payload = {
            "table_name": self.config.table_name,
            "rows": [{self.config.column_email: email}]
        }
        try:
            await self._request("POST", url, json=payload)
            logger.info(f"成功在 SeaTable 中为邮箱 {email} 创建了注册记录行")
            return True
        except SeaTableAPIError:
            raise
