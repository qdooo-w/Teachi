"""
社区/仓库共享工具函数。

本模块提供 community/routes.py、community/library.py、community/admin.py 共用的基础设施：
- 数据库门面解析
- 归档目录操作
- 文件复制
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backend.config import BASE_DIR
from backend.db import DatabaseFacade
from backend.file import FileError


def resolve_db(db_param: Any, module_name: str = "unknown") -> DatabaseFacade:
    """解析并返回数据库门面实例。

    FastAPI 的 Depends(get_db) 在正常运行时直接注入 DatabaseFacade；
    测试或其他调用场景可能传入 None，此时回退到模块级全局变量。

    Args:
        db_param: Depends 注入的参数
        module_name: 调用方模块名，用于错误消息

    Returns:
        DatabaseFacade 实例

    Raises:
        RuntimeError: 无法获取 DatabaseFacade 实例
    """
    if isinstance(db_param, DatabaseFacade):
        return db_param
    raise RuntimeError(f"DatabaseFacade not initialized in {module_name} module")


def archive_root() -> Path:
    """获取归档技能根目录，不存在则自动创建。"""
    root = (BASE_DIR / "archived_skill").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_archive_path(archive_path: str) -> Path:
    """解析归档路径，确保在归档根目录内。

    Args:
        archive_path: 相对路径，如 "archived_skill/{skill_id}/{version}"

    Returns:
        解析后的绝对路径

    Raises:
        FileError: 路径穿越归档根目录
    """
    root = archive_root()
    target = (BASE_DIR / archive_path).resolve()
    if target != root and root not in target.parents:
        raise FileError("Archived skill path is outside archived_skill directory.")
    return target


def copy_skill_dir(src: Path, dst: Path) -> None:
    """复制技能目录。

    Args:
        src: 源目录
        dst: 目标目录（不能已存在）

    Raises:
        FileError: 源不存在或目标已存在
    """
    if not src.is_dir():
        raise FileError("Skill folder not found")
    if dst.exists():
        raise FileError("Target skill folder already exists")
    try:
        shutil.copytree(src, dst)
    except Exception as e:
        raise FileError(str(e)) from e


def directory_size(path: Path) -> int:
    """计算目录下所有文件的总字节数。"""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
