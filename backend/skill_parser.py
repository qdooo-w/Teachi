"""
SKILL.md frontmatter 解析与校验。

后端独立实现一份解析逻辑，不信任前端传来的 name/description，
始终以 SKILL.md 中实际解析出来的字段为准（与 frontend/src/skills.ts 等价）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from backend.config.skill import COMPATIBILITY_MAX, DESCRIPTION_MAX, DISPLAY_NAME_MAX, validate_skill_name

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)


class SkillParseError(ValueError):
    """SKILL.md 解析或校验失败。"""


@dataclass(frozen=True)
class SkillFields:
    name: str
    display_name: str | None
    description: str
    license: str | None
    compatibility: str | None
    version: str | None
    body: str

def parse_skill_file(content: str) -> SkillFields:
    """严格解析 SKILL.md，失败抛 SkillParseError。

    校验规则（与前端 parseSkillFrontmatter 一致）：
    - 必须有完整的 ---\n...\n--- frontmatter 块
    - YAML 必须解析为非空 dict
    - 必须包含非空字符串 name 与 description
    - description ≤ 1024 字符；compatibility ≤ 500 字符
    - name 必须通过 validate_skill_name
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise SkillParseError("缺少 frontmatter 块：文件必须以 `---` 开头并以 `---` 结尾包裹 YAML。")

    fm_text, body = match.group(1), match.group(2)

    try:
        raw = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        raise SkillParseError(f"YAML 语法错误：{e}") from e

    if raw is None:
        raise SkillParseError("frontmatter 为空。")
    if not isinstance(raw, dict):
        raise SkillParseError(
            "frontmatter 必须是键值对形式。常见原因：冒号后漏了空格（正确写法是 `name: foo`）。"
        )

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SkillParseError("frontmatter 必须包含非空字符串字段 `name`。")
    name = name.strip()

    description = raw.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillParseError("frontmatter 必须包含非空字符串字段 `description`。")
    description = description.strip()

    if len(description) > DESCRIPTION_MAX:
        raise SkillParseError(f"description 不能超过 {DESCRIPTION_MAX} 字符（当前 {len(description)}）。")

    name_err = validate_skill_name(name)
    if name_err:
        raise SkillParseError(f"frontmatter.name 不合法：{name_err}")

    display_name_val = raw.get("display_name", raw.get("display-name"))
    if display_name_val is not None and not isinstance(display_name_val, str):
        raise SkillParseError("display_name 必须是字符串。")
    display_name = display_name_val.strip() if isinstance(display_name_val, str) and display_name_val.strip() else None
    if display_name is not None and len(display_name) > DISPLAY_NAME_MAX:
        raise SkillParseError(f"display_name 不能超过 {DISPLAY_NAME_MAX} 字符（当前 {len(display_name)}）。")

    license_val = raw.get("license")
    license_str = license_val.strip() if isinstance(license_val, str) and license_val.strip() else None

    compat_val = raw.get("compatibility")
    compat_str = compat_val.strip() if isinstance(compat_val, str) and compat_val.strip() else None
    if compat_str is not None and len(compat_str) > COMPATIBILITY_MAX:
        raise SkillParseError(
            f"compatibility 不能超过 {COMPATIBILITY_MAX} 字符（当前 {len(compat_str)}）。"
        )

    version_val = raw.get("version")
    if version_val is not None:
        if not isinstance(version_val, (str, int, float)):
            raise SkillParseError("version 必须是字符串（例如 '1.0.0'）。")
        version_str = str(version_val).strip()
    else:
        version_str = None

    return SkillFields(
        name=name,
        display_name=display_name,
        description=description,
        license=license_str,
        compatibility=compat_str,
        version=version_str,
        body=body or "",
    )


def utf8_byte_size(text: str) -> int:
    """与前端 TextEncoder.encode(content).length 等价。"""
    return len(text.encode("utf-8"))
