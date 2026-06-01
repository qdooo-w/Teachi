# 附件上传与视觉工具设计规范

**日期**：2026-06-01  
**范围**：后端（FastAPI + SQLite + PydanticAI）+ 前端（Vue 3）  
**功能**：图片附件上传、`view_attachment` 工具化视觉、多模态/非多模态统一分流

---

## 背景

当前系统不支持附件上传，消息只能传递纯文本。本次设计目标：

1. 支持图片附件上传（初期），架构上预留扩展至 PDF / 文档等其他类型
2. 通过 PydanticAI 工具（`view_attachment`）统一处理图片：多模态模型调工具拿原图；非多模态模型调工具拿精确文字叙述
3. 会话级持久约束注入：有附件时自动在系统提示词中追加"必须调用工具"的强约束

---

## 一、数据层

### 1.1 新增数据库表：`attachments`

```sql
CREATE TABLE IF NOT EXISTS attachments (
    attachment_id   TEXT PRIMARY KEY,
    sid             TEXT NOT NULL REFERENCES sessions(sid) ON DELETE CASCADE,
    user_uuid       TEXT NOT NULL,
    anchor_msg_id   TEXT,
    original_filename TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    description     TEXT,
    description_generated_at REAL,
    created_at      REAL NOT NULL
);
```

**设计说明**：
- `description` 字段为精确内容叙述（不是摘要），强调对图片内容的忠实还原
- `file_path` 为抽象存储路径，本地时为相对路径，未来换 OSS 时存 URL
- `ON DELETE CASCADE`：删除会话时级联删除附件记录

### 1.2 文件存储路径

```
data/{user_uuid}/{pid}/{sid}/attachments/{attachment_id}{.ext}
```

复用现有 `ProjectFile` 门面的安全路径机制（`_safe_path()` 防目录穿越）。

**可扩展性**：路径组织按会话隔离，未来 PDF / 文档附件存入同一目录，`mime_type` 区分处理逻辑。

---

## 二、配置层扩展

### 2.1 `config/model.py` 新增环境变量

| 变量名 | 说明 | 示例 |
|---|---|---|
| `VISION_MODEL_NAME` | 系统默认视觉模型名 | `gpt-4o` |
| `VISION_MODEL_BASE_URL` | 视觉模型 Base URL | `https://api.openai.com/v1` |
| `VISION_MODEL_API_KEY` | 视觉模型 API Key | `sk-...` |
| `VISION_MODEL_WHITELIST` | 已知多模态模型关键词（逗号分隔，模糊匹配） | `gpt-4o,gemini,claude-3` |

### 2.2 `user_model_configs` 表新增字段

```sql
ALTER TABLE user_model_configs ADD COLUMN supports_vision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_model_configs ADD COLUMN is_vision_assistant INTEGER NOT NULL DEFAULT 0;
```

- `supports_vision`：用户手动标记该配置支持视觉（1 = 是）
- `is_vision_assistant`：指定该配置为专用视觉辅助模型（同一用户至多一条为 1）

**视觉能力判断逻辑（优先级）**：
1. 活跃配置的 `model_name` 命中 `VISION_MODEL_WHITELIST` 中任意关键词（大小写不敏感）
2. 活跃配置的 `supports_vision == True`
3. 否则为非视觉模型，工具只返回文字叙述

### 2.3 视觉辅助模型选取优先级

生成图片叙述时：

```
用户配置中 is_vision_assistant=True 的配置
  → 用户配置中 supports_vision=True 的任意一条（取第一条）
    → 系统 env 默认视觉模型（VISION_MODEL_*）
      → 报错：无可用视觉模型
```

---

## 三、API 层

### 3.1 新增接口

#### `POST /sessions/{sid}/attachments`

上传附件，立即落盘，`anchor_msg_id` 为 null（发消息后由 `save_node` 写入）。

**认证**：需要 `Authorization: Bearer <access_token>`  
**请求**：`multipart/form-data`，字段 `file`

限制：
- 仅接受 `image/jpeg`、`image/png`、`image/webp`、`image/gif`
- 单文件 ≤ 10MB（`Content-Length` 超出立即拒绝）
- 校验 magic bytes（防伪造 Content-Type）

**返回 `201 Created`**：

```json
{
  "attachment_id": "uuid",
  "original_filename": "photo.jpg",
  "mime_type": "image/jpeg",
  "created_at": 1748736000.0
}
```

**错误**：

| 状态码 | code | 说明 |
|---|---|---|
| 404 | `RESOURCE_NOT_FOUND` | 会话不存在或不属于当前用户 |
| 413 | `FILE_TOO_LARGE` | 超过 10MB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 不支持的文件类型 |

#### `GET /sessions/{sid}/attachments`

列出会话所有附件（含 `has_description` 标识）。

**返回 `200 OK`**：

```json
{
  "attachments": [
    {
      "attachment_id": "uuid",
      "anchor_msg_id": "msg-uuid-or-null",
      "original_filename": "photo.jpg",
      "mime_type": "image/jpeg",
      "has_description": true,
      "created_at": 1748736000.0
    }
  ]
}
```

#### `DELETE /sessions/{sid}/attachments/{attachment_id}`

删除附件记录及文件实体。返回 `204 No Content`。

### 3.2 `ChatRequest` 扩展（`loop.py`）

```python
attachment_ids: list[str] | None = Field(
    default=None,
    description="本轮附件 ID 列表，save_node 执行后写入 anchor_msg_id"
)
```

`LoopContext` 同步新增 `attachment_ids: list[str] | None = None`。

`save_node` 执行完成后，将 `anchor_msg_id` 写入这些附件记录：

```python
if ctx.attachment_ids and ctx.anchor_msg_id:
    db.attachments.bind_anchor(
        attachment_ids=ctx.attachment_ids,
        anchor_msg_id=ctx.anchor_msg_id,
        user_uuid=ctx.user_uuid,
    )
```

---

## 四、工具层（`tool.py`）

### 4.1 `view_attachment` 工具注册

```python
@register_tool
async def view_attachment(
    ctx: RunContext[ChatDeps],
    attachment_id: str,
) -> ToolReturn:
    """读取附件内容。当用户上传了图片附件时，必须调用此工具后再回答。"""
    db = ctx.deps.db
    user_uuid = ctx.deps.user_uuid

    # 1. 查表校验归属
    attachment = db.attachments.get_for_user(attachment_id, user_uuid)
    if attachment is None:
        return ToolReturn(return_value="错误：附件不存在或无权访问。")

    # 2. 懒生成精确内容叙述
    if attachment["description"] is None:
        description = await _generate_description(attachment, db, user_uuid)
        if description is None:
            return ToolReturn(return_value="错误：无法生成图片叙述，请检查视觉模型配置。")
    else:
        description = attachment["description"]

    # 3. 按主模型视觉能力决定返回内容
    if _active_model_supports_vision(db, user_uuid):
        image_bytes = _read_attachment_file(attachment["file_path"])
        return ToolReturn(
            return_value=description,
            content=[description, BinaryContent(data=image_bytes, media_type=attachment["mime_type"])],
        )
    else:
        return ToolReturn(return_value=description)
```

### 4.2 视觉模型叙述提示词

```
请对这张图片的所有可见内容进行精确、完整的叙述。
包括但不限于：图片中的所有文字（逐字转录）、图表数据与坐标轴标签、
人物描述、场景与背景、颜色与空间关系、代码内容、数学公式等。
不要省略任何细节，不要推断图片以外的内容。
```

叙述生成后写回 `attachments.description` 和 `description_generated_at`。

### 4.3 可扩展性（未来 PDF / 文档）

`view_attachment` 工具内部按 `mime_type` 分支：
- `image/*` → 调视觉模型生成叙述 + 条件返回 `BinaryContent`
- `application/pdf` / `text/*`（未来）→ 提取文本内容直接返回，无需视觉模型

---

## 五、状态机扩展（`node.py`）

### 5.1 `build_model_node` 持久约束注入

构建 Agent 后，查询本会话所有附件，动态追加系统提示约束：

```python
attachments = db.attachments.list_by_session(ctx.sid, ctx.user_uuid)
if attachments:
    lines = [
        f"- {a['original_filename']} (attachment_id: {a['attachment_id']})"
        for a in attachments
    ]
    constraint = (
        "用户在本会话中上传了以下附件：\n"
        + "\n".join(lines)
        + "\n\n当用户的消息与上述附件相关时，"
        "你必须先调用 view_attachment(attachment_id=...) 工具读取附件内容，"
        "再回答用户。不得跳过此步骤。"
    )
    # 追加到现有指令末尾
    base_prompt = load_prompt("init.md", "harness.md", "text_output.md")
    ctx.agent.instructions(base_prompt + "\n\n" + constraint)
```

**约束持久性机制**：约束文本从 `attachments` 表实时构建，无需单独存储。新上传的附件自动进入下一轮的约束文本。

### 5.2 `validate_node` 扩展

`SEND` 动作时，校验 `attachment_ids` 中的每个 ID：
- 存在且归属当前用户
- 归属当前会话（`sid` 匹配）
- `anchor_msg_id` 为 null（未被其他回合绑定）

---

## 六、前端层

### 6.1 `api.ts` 新增方法

```typescript
uploadAttachment(sid: string, file: File): Promise<AttachmentUploadResult>
listAttachments(sid: string): Promise<AttachmentItem[]>
deleteAttachment(sid: string, attachmentId: string): Promise<void>
```

### 6.2 `ChatView.vue` 扩展

- Composer 新增附件按钮（📎）：点击触发文件选择器，`accept="image/*"`，单文件 ≤ 10MB 前端预检
- 选择文件后立即上传，成功后在输入框上方显示图片缩略图 chip（可 × 移除）
- 发送时把所有已上传附件的 `attachment_ids` 携带在 `ChatRequest` 中
- 移除 chip 且附件 `anchor_msg_id` 仍为 null 时，调用 `deleteAttachment` 清理孤立附件

### 6.3 `AIConfigDialog.vue` 扩展

- 模型配置表单新增「支持视觉」复选框（`supports_vision`）
- 新增「设为视觉辅助模型」单选开关（`is_vision_assistant`，同一用户至多一条）

---

## 七、数据库门面扩展（`db.py`）

新增 `AttachmentsFacade`，挂载为 `db.attachments`：

| 方法 | 说明 |
|---|---|
| `create(...)` | 创建附件记录 |
| `get_for_user(attachment_id, user_uuid)` | 校验归属并返回记录 |
| `list_by_session(sid, user_uuid)` | 返回会话所有附件 |
| `bind_anchor(attachment_ids, anchor_msg_id, user_uuid)` | 批量写入 anchor |
| `update_description(attachment_id, description)` | 写入叙述缓存 |
| `delete(attachment_id, user_uuid)` | 删除记录（文件由路由层删） |

---

## 八、未解决项

> [!NOTE]
> 以下事项在实现前需要确认：

1. **REGENERATE 时附件处理**：重放某回合时，原回合绑定的附件应自动携带，`LoopContext` 需能从 `anchor_msg_id` 反查附件列表，无需重新上传
2. **叙述失效机制**：视觉模型配置切换后，旧叙述是否需要强制重新生成？当前设计保留旧叙述（节省 token），如需更新可手动删除附件重传
3. **删除回合时附件清理**：`DELETE /messages/{anchor_msg_id}/turn` 只删消息，附件记录和文件需同步清理（级联或应用层处理）

---

## 九、验证计划

### 自动化测试
- `tests/test_attachments.py`：上传 → 列出 → 绑定 anchor → 删除的完整生命周期
- `tests/test_view_attachment_tool.py`：视觉模型支持/不支持两路返回值
- `tests/test_build_model_node.py`：有/无附件时系统提示词拼接正确性

### 手动验证
- 上传图片 → 发消息 → 确认 `view_attachment` 工具被调用 → 检查 SSE 中出现 `tool_call` 事件
- 切换到非视觉模型配置 → 发同一消息 → 确认工具返回纯文字叙述，模型正常作答
- REGENERATE → 确认叙述从缓存读取，不重复调用视觉模型
