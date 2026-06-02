import re
import os

from backend.config.env import env_int


SKILL_NAME_PATTERN = r"^[\u4e00-\u9fa5a-zA-Z0-9]+(-[\u4e00-\u9fa5a-zA-Z0-9]+)*$"#技能名称的正则表达式模式，要求名称只能包含中文、字母、数字和连字符，且不能以连字符开头或结尾
SKILL_NAME_RE = re.compile(SKILL_NAME_PATTERN)
SKILL_NAME_MAX = 64
SKILL_RESERVED: frozenset[str] = frozenset({"anthropic", "claude","system"})#技能名称中禁止使用的保留词集合，目前包括 "anthropic" 和 "claude"，可能是为了避免与特定品牌或服务名称冲突

SKILL_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml",
})#技能文本文件的允许扩展名集合，包括 Markdown、文本、JSON 和 YAML 文件

SKILL_RESOURCE_DIRS: frozenset[str] = frozenset({"references", "assets", "examples", "templates"})#技能资源目录名称集合，允许的资源目录名称包括 "references" 和 "assets"

SKILL_FILE_MAX_CHARS = env_int(os.getenv("SKILL_FILE_MAX_CHARS"), 512 * 1024)#技能文件最大字符数，默认为 512 * 1024
SKILL_ZIP_MAX_BYTES = env_int(os.getenv("SKILL_ZIP_MAX_BYTES"), 40 * 1024 * 1024)  # 技能压缩包最大字节数，默认 40MB

SKILL_ZIP_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset({
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
})#技能压缩包允许的内容类型集合，包括常见的 ZIP 文件 MIME 类型

SKILL_ZIP_RESOURCE_DIR_ALIASES: dict[str, str] = {
    "reference": "references",
    "references": "references",
    "assets": "assets",
    "example": "examples",
    "examples": "examples",
    "template": "templates",
    "templates": "templates",
}#技能压缩包资源目录别名映射，将上传的 ZIP 文件中的资源目录名称（如 "reference"）映射到标准的资源目录名称（如 "references"），以便统一处理资源目录

DESCRIPTION_MAX = 1024
DISPLAY_NAME_MAX = 80
COMPATIBILITY_MAX = 500


def validate_skill_name(name: str) -> str | None:
    """返回错误信息字符串，合法返回 None。"""
    if not name:
        return "名称不能为空"
    if len(name) > SKILL_NAME_MAX:
        return f"名称不能超过 {SKILL_NAME_MAX} 个字符"
    if not SKILL_NAME_RE.match(name):
        return "名称只能包含中文、字母、数字和连字符，且不能以连字符开头或结尾"
    for reserved in SKILL_RESERVED:
        if reserved in name:
            return f"名称不能包含保留词 {reserved!r}"
    return None
