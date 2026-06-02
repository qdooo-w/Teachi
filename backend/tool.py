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

import logging
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from backend.config.skill import SKILL_TEXT_EXTENSIONS, validate_skill_name

logger = logging.getLogger(__name__)

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


# ── 视觉附件工具 ──────────────────────────────────────────────


async def _generate_description(attachment: dict, db, user_uuid: str) -> str | None:
    """调用视觉辅助模型生成图片精确内容叙述，成功后写入数据库缓存。"""
    from backend.config.model import get_vision_assistant_provider
    from backend.config import BASE_DIR
    from pydantic_ai import Agent, BinaryContent

    file_path_str: str = attachment["file_path"]
    from pathlib import Path
    file_path = (
        Path(file_path_str)
        if Path(file_path_str).is_absolute()
        else BASE_DIR / file_path_str
    )
    mime_type: str = attachment["mime_type"]
    filename_orig = attachment.get("original_filename", file_path.name)

    logger.info("Calling vision assistant model to generate description for image: %s (mime: %s)", filename_orig, mime_type)

    try:
        vision_model = get_vision_assistant_provider(db, user_uuid)
    except RuntimeError as e:
        logger.warning("Failed to get vision assistant provider for user %s: %s", user_uuid, e)
        return None

    if not file_path.is_file():
        logger.warning("Image file does not exist: %s", file_path)
        return None

    image_bytes = file_path.read_bytes()

    describe_prompt = (
        "请对这张图片的所有可见内容进行精确、完整的叙述。"
        "包括但不限于：图片中的所有文字（逐字转录）、图表数据与坐标轴标签、"
        "人物描述、场景与背景、颜色与空间关系、代码内容、数学公式等。"
        "不要省略任何细节，不要推断图片以外的内容。"
    )

    vision_agent = Agent(vision_model)
    try:
        result = await vision_agent.run(
            [describe_prompt, BinaryContent(data=image_bytes, media_type=mime_type)]
        )
        description = result.output if hasattr(result, "output") else str(result.data)
        logger.info("Successfully generated description using vision assistant model (length: %d chars)", len(description))
    except Exception as e:
        logger.exception("Failed to generate description using vision assistant model for %s: %s", filename_orig, e)
        return None

    db.attachments.update_description(attachment["attachment_id"], user_uuid, description)
    return description


def _resolve_skill_resource_path(
    ctx_deps: Any,
    skill_path: str,
) -> Path | None:
    """解析 skill/{scope-prefix}-{skillname}/{filepath} 格式，返回物理文件路径。

    例：skill/project-math-helper/references/notes.md
    返回 None 表示路径非法或文件不存在。
    """
    from backend.context import ChatDeps
    from backend.file import ProjectFile, UserFile

    if not isinstance(ctx_deps, ChatDeps):
        return None

    # 去掉 "skill/" 前缀
    if not skill_path.startswith("skill/"):
        return None
    rest = skill_path[len("skill/"):]
    # 拆分成 scope-name 和 file_path
    parts = rest.split("/", 1)
    if len(parts) != 2 or not parts[1]:
        return None

    scope_name, file_path = parts[0], parts[1]

    # 验证路径安全性（不允许越界）
    path_parts = Path(file_path).parts
    if any(p == ".." for p in path_parts):
        return None
    if file_path.startswith("/") or file_path.startswith("\\"):
        return None

    db = ctx_deps.db
    user_uuid = ctx_deps.user_uuid
    pid = ctx_deps.pid

    try:
        if scope_name.startswith("project-"):
            skill_name = scope_name.removeprefix("project-")
            if err := validate_skill_name(skill_name):
                return None
            fs = ProjectFile(pid=pid, user_uuid=user_uuid, db_facade=db)
        elif scope_name.startswith("user-"):
            skill_name = scope_name.removeprefix("user-")
            if err := validate_skill_name(skill_name):
                return None
            fs = UserFile(user_uuid=user_uuid, db_facade=db)
        elif scope_name.startswith("global-"):
            skill_name = scope_name.removeprefix("global-")
            if err := validate_skill_name(skill_name):
                return None
            fs = UserFile(user_uuid=user_uuid, db_facade=db)  # global 只读，走 user 空间验证
        else:
            return None

        rel = f"skills/{skill_name}/{file_path}"
        phys_path = fs._safe_path(rel)
        return phys_path if phys_path.is_file() else None
    except Exception:
        return None


@register_tool
async def list_attachment(
    ctx: RunContext[Any],
) -> dict[str, Any]:
    """列出当前会话中所有可用的附件（不含 Skill 内部资源）。

    在需要处理附件前先调用此工具获取附件列表，
    再用 view_attachment 读取具体内容。
    Skill 文本资源通过 read_skill_resource 访问；
    Skill 图片等二进制资源可用 view_attachment("skill/{scope}-{name}/{filepath}") 读取。

    Returns:
        {"attachments": [{"filename", "mime_type", "file_size"}]}
    """
    from backend.context import ChatDeps

    if not isinstance(ctx.deps, ChatDeps):
        return {"status": "error", "error": "deps_missing"}

    db = ctx.deps.db
    user_uuid = ctx.deps.user_uuid
    sid = ctx.deps.sid

    rows = db.attachments.list_by_session(sid=sid, user_uuid=user_uuid)
    return {
        "attachments": [
            {
                "filename": r["original_filename"],
                "mime_type": r["mime_type"],
                "file_size": r.get("file_size", 0),
            }
            for r in rows
        ]
    }


@register_tool
async def view_attachment(
    ctx: RunContext[Any],
    filename: str,
) -> Any:
    """读取附件内容。

    支持两种调用格式：

    1. 普通附件：filename 为会话内的友好文件名（例如 "图片1.png", "文档2.txt"）
       - 图片：返回内容叙述文字（视觉模型生成），支持视觉的主模型同时获得原图；
       - 文本/JSON/CSV/Markdown：直接返回文件内容；
       - PDF：返回提示信息（暂不支持解析，请联系用户手动处理）。

    2. Skill 资源路径：filename = "skill/{scope-prefix}-{skillname}/{filepath}"
       例：skill/project-math-helper/references/notes.md
       - 只支持文本类资源（.md/.txt/.json/.yaml/.yml/.csv/.xml）；
       - 图片类 Skill 资源返回 BinaryContent 给主模型直接查看。

    Args:
        filename: 友好文件名 或 "skill/{scope}-{name}/{filepath}" 格式路径。
    """
    from pydantic_ai import ToolReturn, BinaryContent
    from backend.context import ChatDeps
    from backend.config.model import active_model_supports_vision
    from pathlib import Path
    from backend.config import BASE_DIR

    if not isinstance(ctx.deps, ChatDeps):
        return ToolReturn(return_value="错误：工具依赖未正确注入。")

    db = ctx.deps.db
    user_uuid = ctx.deps.user_uuid

    IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    TEXT_MIMES = {
        "text/plain", "text/markdown", "text/csv", "text/html",
        "application/json",
    }

    # ── 分支 1：Skill 资源路径 ──────────────────────────────
    if filename.startswith("skill/"):
        phys_path = _resolve_skill_resource_path(ctx.deps, filename)
        if phys_path is None:
            return ToolReturn(return_value="错误：Skill 资源路径不存在或非法。")

        suffix = phys_path.suffix.lower()
        # 文本资源
        if suffix in SKILL_TEXT_EXTENSIONS:
            try:
                content = phys_path.read_text(encoding="utf-8")
                return ToolReturn(return_value=content)
            except Exception as e:
                return ToolReturn(return_value=f"错误：读取 Skill 资源失败：{e}")

        # 图片资源（直接返回 BinaryContent）
        image_ext_to_mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
        }
        if suffix in image_ext_to_mime:
            try:
                img_bytes = phys_path.read_bytes()
                mime = image_ext_to_mime[suffix]
                return ToolReturn(
                    return_value=f"Skill 图片资源：{phys_path.name}",
                    content=[BinaryContent(data=img_bytes, media_type=mime)],
                )
            except Exception as e:
                return ToolReturn(return_value=f"错误：读取 Skill 图片失败：{e}")

        return ToolReturn(return_value=f"错误：不支持的 Skill 资源类型：{suffix}")

    # ── 分支 2：普通附件 ───────────────────────────────────
    attachment = db.attachments.get_by_filename(ctx.deps.sid, filename, user_uuid)
    if attachment is None:
        return ToolReturn(return_value="错误：附件不存在或无权访问。")

    mime_type: str = attachment["mime_type"]
    file_path_str: str = attachment["file_path"]
    file_path = (
        Path(file_path_str)
        if Path(file_path_str).is_absolute()
        else BASE_DIR / file_path_str
    )

    if not file_path.is_file():
        return ToolReturn(return_value="错误：附件文件不存在，可能已被删除。")

    # 文本类型：直接返回内容
    if mime_type in TEXT_MIMES:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            filename_orig = attachment.get("original_filename", file_path.name)
            return ToolReturn(return_value=f"[{filename_orig}]\n\n{text}")
        except Exception as e:
            return ToolReturn(return_value=f"错误：读取文本附件失败：{e}")

    # PDF：暂不解析
    if mime_type == "application/pdf":
        filename_orig = attachment.get("original_filename", "")
        return ToolReturn(
            return_value=(
                f"附件「{filename_orig}」是 PDF 文件，当前版本暂不支持自动解析，"
                "请告知用户手动提取所需内容后重新粘贴。"
            )
        )

    # 图片：生成叙述（走缓存），视觉模型同时返回 BinaryContent
    if mime_type in IMAGE_MIMES:
        filename_orig = attachment.get("original_filename", file_path.name)
        logger.info("view_attachment called for image: %s (mime: %s)", filename_orig, mime_type)

        description: str | None = attachment.get("description")
        if description is None:
            logger.info("No cached description found for %s. Generating new description...", filename_orig)
            description = await _generate_description(attachment, db, user_uuid)
            if description is None:
                logger.error("Failed to generate description for %s", filename_orig)
                return ToolReturn(return_value="错误：无法生成图片内容叙述，请让用户检查/反馈视觉模型配置。")
        else:
            logger.info("Using cached description for %s", filename_orig)

        if active_model_supports_vision(db, user_uuid):
            logger.info("Active model supports vision. Returning both description and BinaryContent for %s", filename_orig)
            image_bytes = file_path.read_bytes()
            return ToolReturn(
                return_value=description,
                content=[description, BinaryContent(data=image_bytes, media_type=mime_type)],
            )
        else:
            logger.info("Active model does NOT support vision. Returning description text only for %s", filename_orig)
            return ToolReturn(return_value=description)

    return ToolReturn(return_value=f"错误：不支持的附件类型 {mime_type!r}。")

