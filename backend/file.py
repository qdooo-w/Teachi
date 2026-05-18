import logging
import re
import shutil
from pathlib import Path
from typing import Union, List, Dict, Optional

from backend.config import BASE_DIR

logger = logging.getLogger(__name__)


class FileError(Exception):
    """文件操作基本错误类"""
    pass

# 文本文件扩展名白名单，供 HTTP API 使用
_TEXT_FILE_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".xml"
})

# 文件操作方法白名单，供 File_Handler 和 Skill_Handler 使用
_ALLOWED_FS_METHODS: set[str] = {
    "create_file", "delete_file", "create_dir", "delete_dir", "read_file", "search_dir",
}

class FileBase:
    """
    文件系统 Facade 基类。
    所有操作限制在 self.base_path 之下。
    """
    def __init__(self, base_path: Union[str, Path]):
        self.base_path = Path(base_path).resolve()
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, relative_path: str) -> Path:
        """安全路径转换，防止路径穿越攻击。"""
        clean_rel = relative_path.lstrip("/\\")
        target_path = (self.base_path / clean_rel).resolve()

        if target_path != self.base_path and self.base_path not in target_path.parents:
            raise FileError(f"Access denied: Path {relative_path} is outside base directory.")
        return target_path

    def create_file(self, path: str, content: str = "") -> str:
        """创建文件或覆盖已有文件。"""
        try:
            target = self._safe_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"File created: {path}"
        except Exception as e:
            raise FileError(f"Failed to create file {path}: {e}")

    def delete_file(self, path: str) -> str:
        """删除指定路径的文件。"""
        try:
            target = self._safe_path(path)
            if target.is_file():
                target.unlink()
                return f"File deleted: {path}"
            raise FileError(f"Path is not a file: {path}")
        except Exception as e:
            raise FileError(f"Failed to delete file {path}: {e}")

    def create_dir(self, path: str) -> str:
        """创建文件夹（递归）。"""
        try:
            target = self._safe_path(path)
            target.mkdir(parents=True, exist_ok=True)
            return f"Directory created: {path}"
        except Exception as e:
            raise FileError(f"Failed to create directory {path}: {e}")

    def delete_dir(self, path: str) -> str:
        """递归删除文件夹。"""
        try:
            target = self._safe_path(path)
            if target.is_dir():
                shutil.rmtree(target)
                return f"Directory deleted: {path}"
            raise FileError(f"Path is not a directory: {path}")
        except Exception as e:
            raise FileError(f"Failed to delete directory {path}: {e}")

    def read_file(self, path: str) -> str:
        """读取文件内容。"""
        try:
            target = self._safe_path(path)
            if not target.is_file():
                raise FileError(f"File not found: {path}")
            return target.read_text(encoding="utf-8")
        except Exception as e:
            raise FileError(f"Failed to read file {path}: {e}")

    def search_dir(self, path: str = ".") -> List[Dict[str, Union[str, bool, int, float]]]:
        """搜索目录下文件和文件夹结构。"""
        try:
            target = self._safe_path(path)
            if not target.is_dir():
                raise FileError(f"Directory not found: {path}")

            results = []
            for item in target.iterdir():
                stat = item.stat()
                results.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "rel_path": str(item.relative_to(self.base_path)),
                    "size": 0 if item.is_dir() else stat.st_size,
                    "updated_at": stat.st_mtime,
                })
            return results
        except FileError:
            raise
        except Exception as e:
            raise FileError(f"Failed to search directory {path}: {e}")

class ProjectFile(FileBase):
    """
    项目文件子类，限制在 data/{user_uuid}/{pid}。
    """
    def __init__(self, pid: str, user_uuid: str, db_facade):
        project = db_facade.projects.get_for_user(pid=pid, user_uuid=user_uuid)
        if not project:
            raise PermissionError(f"Access Denied: Project {pid} does not belong to user {user_uuid}")

        project_path = BASE_DIR / "data" / user_uuid / pid
        super().__init__(project_path)

class UserFile(FileBase):
    """
    用户文件子类，限制在 data/{user_uuid}。
    """
    def __init__(self, user_uuid: str, db_facade):
        user = db_facade.users.get_by_uuid(user_uuid)
        if not user:
            raise PermissionError(f"Access Denied: User {user_uuid} not found")

        user_path = BASE_DIR / "data" / user_uuid
        super().__init__(user_path)


# ── Skill 文件门面 ──────────────────────────────────────────────
# 设计目标：让 AI 在人类指令下读写 skill 目录中的文本文件，
# 但操作面被严格收敛，不能逃出 skills/ 子目录、不能写非文本文件、不能超大。

# 与 frontend/src/skills.ts 保持一致的 skill 名称约束（kebab-case，≤64）
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SKILL_NAME_MAX = 64
_SKILL_NAME_RESERVED: frozenset[str] = frozenset({"anthropic", "claude"})

# 文本文件扩展名白名单（独立于 _TEXT_FILE_EXTENSIONS，避免被无关接口扩散影响）
_SKILL_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".xml",
})


def _validate_skill_name(skill_name: str) -> None:
    """校验 skill 名：kebab-case、长度 ≤64、不在保留词内。"""
    if not isinstance(skill_name, str) or not skill_name:
        raise FileError("skill name must be a non-empty string")
    if len(skill_name) > _SKILL_NAME_MAX:
        raise FileError(f"skill name too long (>{_SKILL_NAME_MAX} chars)")
    if not _SKILL_NAME_RE.match(skill_name):
        raise FileError("skill name must match ^[a-z0-9]+(-[a-z0-9]+)*$")
    if skill_name in _SKILL_NAME_RESERVED:
        raise FileError(f"skill name '{skill_name}' is reserved")


def _validate_skill_relpath(rel_path: str) -> None:
    """校验 skill 内部相对路径：非空、扩展名在白名单、无穿越元字符。

    `_safe_path` 已用 resolve() 阻止穿越；这里再做一道字面量黑名单，
    便于在更早的位置返回明确错误。
    """
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise FileError("path must be a non-empty string")
    if "\x00" in rel_path:
        raise FileError("path contains NUL byte")
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise FileError("path must be relative, not absolute")
    # 阻止显式的父级穿越段（resolve 仍会兜底）
    parts = Path(rel_path).parts
    if any(p == ".." for p in parts):
        raise FileError("path must not contain '..' segments")
    suffix = Path(rel_path).suffix.lower()
    if suffix not in _SKILL_TEXT_EXTENSIONS:
        raise FileError(
            f"unsupported file extension '{suffix}'. allowed: "
            f"{sorted(_SKILL_TEXT_EXTENSIONS)}"
        )


