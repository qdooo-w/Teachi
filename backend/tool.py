"""
tool.py - AI 工具定义与组装模块

本模块职责：
1. 定义工具函数的执行逻辑（文件读取、目录遍历等）。
2. 维护工具注册表（register_tool / _TOOL_REGISTRY / _REGISTERED_TOOL_NAMES）。
3. 提供 build_tools，根据 allowed 参数过滤并构建 Agent 可用的 Tool 列表。

与其他模块关系：
- loop.py：负责模型编排与重试，通过 build_tools 注入可调用工具。
- data.py / main.py：负责路由和应用挂载，不参与工具执行。
- db.py：不直接耦合；工具如需业务依赖，统一通过 RunContext.deps 获取。

如何新增一个可被 AI 调用的工具：
1. 在本文件新增函数，首参使用 ctx: RunContext[Any]。
2. 返回值约定为 dict[str, Any]（成功/错误都走结构化返回）。
3. 使用 @register_tool 装饰器注册，函数名即工具名。
4. 无需改 loop.py，Agent 启动时会通过 build_tools 自动纳入。

调用链路：
register_tool -> build_tools(allowed=...) -> Agent(tools=...) -> 工具函数执行
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from backend.config.skill import SKILL_TEXT_EXTENSIONS, validate_skill_name

# 已注册工具名称集合，用于快速查找和权限校验
_REGISTERED_TOOL_NAMES: set[str] = set()

# 工具函数注册表：name → function，由 build_tools 读取并包装为 Tool 对象
_TOOL_REGISTRY: dict[str, Any] = {}


def register_tool(func: Any) -> Any:
    """
    工具注册装饰器。

    行为：
    1. 使用函数名作为工具名写入 _REGISTERED_TOOL_NAMES。
    2. 将函数对象写入 _TOOL_REGISTRY。
    3. 返回原函数，不改变调用方式。

    约定：工具函数签名应为 (ctx: RunContext[Any], ...params) -> dict[str, Any]。
    """
    tool_name = func.__name__
    _REGISTERED_TOOL_NAMES.add(tool_name)
    _TOOL_REGISTRY[tool_name] = func
    return func


def get_registered_tool_names() -> set[str]:
    """
    返回已注册工具名集合的副本。

    返回副本而非原集合，避免外部代码误改内部注册状态。
    """
    return set(_REGISTERED_TOOL_NAMES)


def get_tool_registry() -> dict[str, Any]:
    """
    返回工具注册表副本。

    键为工具名，值为函数对象，供 build_tools 进行统一包装。
    """
    return dict(_TOOL_REGISTRY)


def build_tools(allowed: list[str] | None = None) -> list[Tool[Any]]:
    """根据注册表和 allowed 过滤，构建 Pydantic AI Tool 列表。

    参数:
        allowed: 允许的工具名列表。None 表示返回所有已注册工具。

    返回:
        只包含已注册且在 allowed 范围内的 Tool 对象列表。
    """
    tool_registry = get_tool_registry()
    allowed_set = set(allowed) if allowed else None
    tools: list[Tool[Any]] = []
    for tool_name, func in tool_registry.items():
        if allowed_set is not None and tool_name not in allowed_set:
            continue
        tools.append(Tool(func))
    return tools



# ============================================================
# 工具函数定义区域
# 在此处添加新的工具函数，使用 @register_tool 装饰器注册
#
# 注意：
# 1. 工具函数的第一个参数必须是 RunContext（Pydantic AI 要求）
# 2. 这里使用 RunContext[Any] 避免循环导入，实际类型是 RunContext[ChatDeps]
# 3. 工具必须带有说明，只要在修饰器修饰的那个函数做好""""""的注释即可，可以把参数和目的写好点
# ============================================================


def _parse_skill_ref(skill_ref: str) -> tuple[str, str]:
    """把 AI 看到的技能引用拆成 scope 和真实 skill_name。"""
    if not isinstance(skill_ref, str) or not skill_ref:
        raise ValueError("skill_ref must be a non-empty string")
    if skill_ref.startswith("global-"):
        raise ValueError("global skills are read-only")
    if skill_ref.startswith("project-"):
        skill_name = skill_ref.removeprefix("project-")
        if not skill_name:
            raise ValueError("skill_ref must include a project skill name")
        if err := validate_skill_name(skill_name):
            raise ValueError(f"invalid skill name: {err}")
        return "project", skill_name
    if skill_ref.startswith("user-"):
        skill_name = skill_ref.removeprefix("user-")
        if not skill_name:
            raise ValueError("skill_ref must include a user skill name")
        if err := validate_skill_name(skill_name):
            raise ValueError(f"invalid skill name: {err}")
        return "user", skill_name
    raise ValueError("skill_ref must start with project- or user-")


def _skill_rel_path(skill_name: str, file_path: str) -> str:
    """生成 skills/<skill_name>/<file_path>，并阻止越界路径。"""
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path must be a non-empty string")
    if file_path.startswith("/") or file_path.startswith("\\"):
        raise ValueError("file_path must be relative")
    if "\x00" in file_path:
        raise ValueError("file_path contains NUL byte")
    parts = Path(file_path).parts
    if any(part == ".." for part in parts):
        raise ValueError("file_path must not contain '..'")
    suffix = Path(file_path).suffix.lower()
    if suffix not in SKILL_TEXT_EXTENSIONS:
        raise ValueError(f"unsupported file extension '{suffix}'")
    return f"skills/{skill_name}/{file_path}"


def _with_skill_fs(ctx: RunContext[Any], skill_ref: str, fn) -> dict[str, Any]:
    """构造对应范围的文件门面并执行 fn(fs)，统一把异常转为结构化返回。"""
    from backend.context import ChatDeps  # 避免顶层循环依赖
    from backend.file import ProjectFile, UserFile, FileError

    if not isinstance(ctx.deps, ChatDeps):
        return {"status": "error", "error": "deps_missing"}

    db = ctx.deps.db
    try:
        scope, _skill_name = _parse_skill_ref(skill_ref)
        if scope == "user":
            fs = UserFile(user_uuid=ctx.deps.user_uuid, db_facade=db)
        else:
            fs = ProjectFile(pid=ctx.deps.pid, user_uuid=ctx.deps.user_uuid, db_facade=db)
        return {"status": "success", "result": fn(fs)}
    except (FileError, ValueError) as e:
        return {"status": "error", "error": "file_operation_failed", "message": str(e)}
    except PermissionError as e:
        return {"status": "error", "error": "permission_denied", "message": str(e)}
    except Exception as e:  # noqa: BLE001 - 转结构化返回，避免冒泡到模型循环
        return {"status": "error", "error": "internal_error", "message": str(e)}


@register_tool
async def write_skill_file(
    ctx: RunContext[Any],
    skill_ref: str,
    file_path: str,
    content: str,
) -> dict[str, Any]:
    """Create or overwrite a text file inside a skill directory. Parent dirs auto-created.

    USE THIS to author or update a Claude-style Skill on the user's behalf.
    Do NOT use it to read existing skills — use the built-in `list_skills`,
    `load_skill`, or `read_skill_resource` tools instead.

    The model should pass the skill reference it sees in context:
    - `project-<skill_name>` for the current project's skills
    - `user-<skill_name>` for the user's private skills

    The tool strips that prefix internally and writes to the matching scope.
    `global-*` skills are read-only and will be rejected.

    SKILL.md format (required for every skill):

        ---
        name: <kebab-case skill name, matches folder name>
        description: <one-sentence trigger; tell the model WHEN to load this skill>
        ---

        # <Skill title>

        <Body: instructions, examples, references. Markdown.>

    Frontmatter rules:
      - `name` and `description` are required.
      - `name` must match `^[a-z0-9]+(-[a-z0-9]+)*$`, length ≤ 64,
        and must not be `anthropic` or `claude`.
      - `description` should be a single-sentence trigger like
        "Use when the user asks for X" so the router model picks it correctly.
      - Optional fields: `license`, `compatibility` (each ≤ 500 chars).
      - Use a YAML library, not hand-rolled string concat — colons and quotes
        in `description` will silently break the frontmatter otherwise.

    Layout convention:
      - `SKILL.md`                — entry point, always present.
      - `references/*.md`         — long-form notes, loaded on demand via
                                    `read_skill_resource`.
      - `assets/*.{json,yaml,…}`  — structured data the skill body references.
      - `examples/*`              — example files for the skill.
      - `templates/*`             — template files for the skill.
      Body of SKILL.md should stay short; push detail into `references/`.

    Recommended workflow when creating a new skill:
      1. Pick `skill_name` (kebab-case) and call it through `project-<skill_name>`
         or `user-<skill_name>`.
      2. Call this tool once with `file_path="SKILL.md"` and the full
         frontmatter + body.
      3. Optionally call again with `file_path="references/<topic>.md"`
         for any supporting docs.
      Updating an existing skill is the same — overwrite `SKILL.md`
      or any single resource file in place.

    Constraints (will return a structured error otherwise):
      - `file_path` extension must be one of:
        .md / .txt / .json / .yaml / .yml / .csv / .xml
      - `file_path` must be relative and stay inside the skill folder
        (no `..`, no leading `/`).

    Args:
        skill_ref: scoped skill name shown to the model, e.g. `project-math-helper`
            or `user-writing-style`.
        file_path: relative path inside the skill folder, e.g. `"SKILL.md"`,
            `"references/notes.md"`, `"assets/data.json"`, `"examples/demo.json"`, `"templates/template.txt"`.
        content: full UTF-8 text content. For `SKILL.md`, MUST start with
            a YAML frontmatter block delimited by `---`.

    Returns:
        On success: `{"status": "success", "result": {"rel_path", "size", "updated_at"}}`.
        On failure: `{"status": "error", "error": <code>, "message": <detail>}`
        with `error` one of `permission_denied` / `file_operation_failed` /
        `deps_missing` / `internal_error`.
    """
    def _write(fs: Any) -> Any:
        _scope, skill_name = _parse_skill_ref(skill_ref)
        rel_path = _skill_rel_path(skill_name, file_path)
        fs.create_file(rel_path, content)
        target = fs._safe_path(rel_path)
        stat = target.stat()
        return {
            "rel_path": rel_path,
            "size": stat.st_size,
            "updated_at": stat.st_mtime,
        }

    return _with_skill_fs(ctx, skill_ref, _write)


@register_tool
async def delete_skill_file(
    ctx: RunContext[Any],
    skill_ref: str,
    file_path: str,
) -> dict[str, Any]:
    """Delete a single text file inside a skill directory. Does not remove directories.

    Use this only when the user explicitly asks to remove a specific resource
    file from a skill (e.g. an outdated `references/foo.md`). To delete the
    whole skill, use `delete_skill` instead. Deleting `SKILL.md` is allowed
    but leaves an invalid skill folder — usually you want `delete_skill`.

    Args:
        skill_ref: scoped skill name shown to the model, e.g. `project-math-helper`.
        file_path: relative path inside the skill folder. Extension must be
            in the text whitelist (.md/.txt/.json/.yaml/.yml/.csv/.xml).

    Returns:
        On success: `{"status": "success", "result": "deleted: <skill>/<file>"}`.
        On failure: `{"status": "error", "error": <code>, "message": <detail>}`.
    """
    def _delete(fs: Any) -> Any:
        _scope, skill_name = _parse_skill_ref(skill_ref)
        rel_path = _skill_rel_path(skill_name, file_path)
        fs.delete_file(rel_path)
        return f"deleted: {skill_name}/{file_path}"

    return _with_skill_fs(ctx, skill_ref, _delete)


@register_tool
async def delete_skill(
    ctx: RunContext[Any],
    skill_ref: str,
) -> dict[str, Any]:
    """Recursively delete an entire skill directory. DESTRUCTIVE — confirm with the user first.

    Removes the folder for the referenced skill and everything in it,
    including `SKILL.md` and all resources. There is no undo.

    Pass `project-<skill_name>` for project skills or `user-<skill_name>` for
    user skills. `global-*` skills are read-only.

    Only call when the user has clearly asked to delete the whole skill.
    For removing a single file inside a skill, use `delete_skill_file`.
    For replacing skill contents, just call `write_skill_file` to overwrite —
    no need to delete first.

    Args:
        skill_ref: scoped skill name shown to the model, e.g. `project-math-helper`.

    Returns:
        On success: `{"status": "success", "result": "skill deleted: <skill>"}`.
        On failure: `{"status": "error", "error": <code>, "message": <detail>}`.
    """
    def _delete_skill(fs: Any) -> Any:
        _scope, skill_name = _parse_skill_ref(skill_ref)
        rel_path = f"skills/{skill_name}"
        fs.delete_dir(rel_path)
        return f"skill deleted: {skill_name}"

    return _with_skill_fs(ctx, skill_ref, _delete_skill)
