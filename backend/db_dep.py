"""db_dep.py - 单例 DatabaseFacade 的 FastAPI 依赖注入点"""

from backend.config import DATABASE_PATH
from backend.db import DatabaseFacade

db = DatabaseFacade(db_path=DATABASE_PATH)


def get_db() -> DatabaseFacade:
    return db
