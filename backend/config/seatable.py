# backend/config/seatable.py

import os
from typing import Dict


class SeaTableConfig:
    """SeaTable 配置类，从环境变量读取配置"""

    def __init__(self):
        self.server_url = self._require_env("SEATABLE_SERVER_URL").rstrip("/")
        self.api_token = self._require_env("SEATABLE_API_TOKEN")
        self.base_uuid = self._require_env("SEATABLE_BASE_UUID")
        self.table_name = self._require_env("SEATABLE_TABLE_NAME")
        self.column_map: Dict[str, str] = {
            "email": self._require_env("SEATABLE_COLUMN_EMAIL"),
            "code": self._require_env("SEATABLE_COLUMN_CODE"),
            "status": self._require_env("SEATABLE_COLUMN_STATUS"),
            "expires": self._require_env("SEATABLE_COLUMN_EXPIRES"),
        }

    @staticmethod
    def _require_env(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

    @property
    def column_email(self) -> str:
        return self.column_map["email"]

    @property
    def column_code(self) -> str:
        return self.column_map["code"]

    @property
    def column_status(self) -> str:
        return self.column_map["status"]

    @property
    def column_expires(self) -> str:
        return self.column_map["expires"]
