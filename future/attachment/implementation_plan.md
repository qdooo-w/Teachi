# 附件上传与视觉工具实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Teachi 后端添加图片附件上传功能，并通过 PydanticAI `view_attachment` 工具统一处理多模态/非多模态分流。

**Architecture:** 附件记录存 `attachments` 表（绑定会话和回合），图片文件存 `data/{user_uuid}/{pid}/{sid}/attachments/` 目录。`view_attachment` 工具懒生成图片内容叙述缓存，按主模型视觉能力决定返回 `BinaryContent`（原图）或纯文字叙述。`build_model_node` 查询会话附件后动态注入强约束系统提示词。

**Tech Stack:** FastAPI, SQLite (sqlite3), PydanticAI (`BinaryContent`, `ToolReturn`, `RunContext`), Python 3.13, Vue 3 + TypeScript (前端任务)

---

## 参考文档

设计规范：`/home/seeck/.gemini/antigravity/brain/1d791ae4-db19-4809-95da-31f1637423e2/attachment-vision-tool-design.md`

---

## 文件改动总览

| 文件 | 操作 | 说明 |
|---|---|---|
| `backend/db.py` | 修改 | 新增 `AttachmentsFacade`，挂载到 `DatabaseFacade`；`setup_database` 新增 `attachments` 表和迁移 |
| `backend/config/model.py` | 修改 | 新增视觉模型环境变量（`VISION_MODEL_*`）、白名单、辅助模型选取函数 |
| `backend/data.py` | 修改 | 新增 `POST/GET/DELETE /sessions/{sid}/attachments` 三个路由 |
| `backend/context.py` | 修改 | `LoopContext` 新增 `attachment_ids: list[str] | None` 字段 |
| `backend/loop.py` | 修改 | `ChatRequest` 新增 `attachment_ids` 字段；创建 `LoopContext` 时传入 |
| `backend/node.py` | 修改 | `validate_node` 校验 attachment_ids；`save_node` 绑定 anchor；`build_model_node` 注入约束提示词 |
| `backend/tool.py` | 修改 | 新增 `view_attachment` 工具和 `_generate_description` 辅助函数 |
| `backend/file.py` | 修改 | 新增 `SessionFile` 类，作用域 `data/{user_uuid}/{pid}/{sid}/` |
| `tests/test_attachments_db.py` | 新建 | `AttachmentsFacade` 单元测试 |
| `tests/test_attachments_api.py` | 新建 | 附件 API 集成测试 |
| `tests/test_view_attachment_tool.py` | 新建 | `view_attachment` 工具测试 |
| `frontend/src/api.ts` | 修改 | 新增 `uploadAttachment`、`listAttachments`、`deleteAttachment` |
| `frontend/src/views/ChatView.vue` | 修改 | 新增附件按钮、缩略图 chip、发送时携带 `attachment_ids` |
| `frontend/src/components/AIConfigDialog.vue` | 修改 | 新增 `supports_vision` 和 `is_vision_assistant` 字段 |

---

## Task 1: 数据层 — `attachments` 表 + `AttachmentsFacade` + `user_model_configs` 扩展

**Files:**
- Modify: `backend/db.py`
- Create: `tests/test_attachments_db.py`

---

- [ ] **Step 1: 写失败测试**

新建 `tests/test_attachments_db.py`：

```python
import pytest
from backend.db import DatabaseFacade


@pytest.fixture
def db(tmp_path):
    facade = DatabaseFacade(db_path=str(tmp_path / "test.db"))
    facade.setup_database()
    return facade


@pytest.fixture
def user(db):
    import hashlib
    pw_hash = hashlib.pbkdf2_hmac("sha256", b"pw", b"salt", 120000).hex()
    return db.users.create("testuser", "test@example.com", pw_hash)


@pytest.fixture
def project(db, user):
    return db.projects.create("Test Project", user["uuid"])


@pytest.fixture
def session(db, project):
    return db.sessions.create(project["pid"], "Test Session")


def test_create_attachment(db, user, session):
    att = db.attachments.create(
        sid=session["sid"],
        user_uuid=user["uuid"],
        original_filename="photo.jpg",
        file_path="data/u/p/s/attachments/att1.jpg",
        mime_type="image/jpeg",
    )
    assert att["attachment_id"] is not None
    assert att["anchor_msg_id"] is None
    assert att["description"] is None
    assert att["mime_type"] == "image/jpeg"


def test_get_for_user(db, user, session):
    att = db.attachments.create(
        sid=session["sid"], user_uuid=user["uuid"],
        original_filename="img.png", file_path="some/path.png", mime_type="image/png",
    )
    found = db.attachments.get_for_user(att["attachment_id"], user["uuid"])
    assert found is not None
    assert found["original_filename"] == "img.png"


def test_get_for_user_wrong_user(db, user, session):
    att = db.attachments.create(
        sid=session["sid"], user_uuid=user["uuid"],
        original_filename="img.png", file_path="some/path.png", mime_type="image/png",
    )
    assert db.attachments.get_for_user(att["attachment_id"], "wrong-user") is None


def test_list_by_session(db, user, session):
    db.attachments.create(sid=session["sid"], user_uuid=user["uuid"],
        original_filename="a.jpg", file_path="p1", mime_type="image/jpeg")
    db.attachments.create(sid=session["sid"], user_uuid=user["uuid"],
        original_filename="b.png", file_path="p2", mime_type="image/png")
    items = db.attachments.list_by_session(session["sid"], user["uuid"])
    assert len(items) == 2


def test_bind_anchor(db, user, session):
    att = db.attachments.create(
        sid=session["sid"], user_uuid=user["uuid"],
        original_filename="x.jpg", file_path="p", mime_type="image/jpeg",
    )
    db.attachments.bind_anchor(
        attachment_ids=[att["attachment_id"]],
        anchor_msg_id="anchor-123",
        user_uuid=user["uuid"],
    )
    updated = db.attachments.get_for_user(att["attachment_id"], user["uuid"])
    assert updated["anchor_msg_id"] == "anchor-123"


def test_update_description(db, user, session):
    att = db.attachments.create(
        sid=session["sid"], user_uuid=user["uuid"],
        original_filename="x.jpg", file_path="p", mime_type="image/jpeg",
    )
    db.attachments.update_description(att["attachment_id"], "一张猫咪的图片，白色，坐在窗台上。")
    updated = db.attachments.get_for_user(att["attachment_id"], user["uuid"])
    assert updated["description"] == "一张猫咪的图片，白色，坐在窗台上。"
    assert updated["description_generated_at"] is not None


def test_delete_attachment(db, user, session):
    att = db.attachments.create(
        sid=session["sid"], user_uuid=user["uuid"],
        original_filename="x.jpg", file_path="p", mime_type="image/jpeg",
    )
    assert db.attachments.delete(att["attachment_id"], user["uuid"]) is True
    assert db.attachments.get_for_user(att["attachment_id"], user["uuid"]) is None


def test_user_model_config_supports_vision(db, user):
    config = db.model_configs.create(
        user_uuid=user["uuid"],
        config_name="test-vision",
        supports_vision=True,
        is_vision_assistant=True,
    )
    assert config["supports_vision"] == True
    assert config["is_vision_assistant"] == True
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/seeck/Projects/Teachi
uv run pytest tests/test_attachments_db.py -v
```

期望：FAILED — `db.attachments` 不存在，`model_configs.create` 不接受 `supports_vision`

- [ ] **Step 3: 实现 `AttachmentsFacade`**

在 `backend/db.py` 中，`CommunitySkillsFacade` 类结束后、`DatabaseFacade` 之前，添加：

```python
class AttachmentsFacade(_DataBase):
    """图片附件管理。每条记录绑定一个会话，save_node 执行后绑定到 anchor_msg_id。"""

    _COLUMNS = (
        "attachment_id, sid, user_uuid, anchor_msg_id, original_filename, "
        "file_path, mime_type, description, description_generated_at, created_at"
    )

    def create(
        self,
        *,
        sid: str,
        user_uuid: str,
        original_filename: str,
        file_path: str,
        mime_type: str,
    ) -> dict:
        attachment_id = str(uuid.uuid4())
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO attachments
                    (attachment_id, sid, user_uuid, original_filename, file_path,
                     mime_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (attachment_id, sid, user_uuid, original_filename, file_path, mime_type, now_ts),
            )
        record = self.get_for_user(attachment_id, user_uuid)
        if record is None:
            raise RuntimeError("Attachment was inserted but could not be loaded.")
        return record

    def get_for_user(self, attachment_id: str, user_uuid: str) -> dict | None:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE attachment_id = ? AND user_uuid = ?",
                (attachment_id, user_uuid),
            )
            row = cursor.fetchone()
        return self._row_to_dict(row)

    def list_by_session(self, sid: str, user_uuid: str) -> list[dict]:
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT {self._COLUMNS} FROM attachments WHERE sid = ? AND user_uuid = ? ORDER BY created_at ASC",
                (sid, user_uuid),
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def bind_anchor(self, *, attachment_ids: list[str], anchor_msg_id: str, user_uuid: str) -> int:
        """把一组附件的 anchor_msg_id 写入指定回合锚点。"""
        if not attachment_ids:
            return 0
        placeholders = ",".join("?" * len(attachment_ids))
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE attachments SET anchor_msg_id = ?
                WHERE attachment_id IN ({placeholders}) AND user_uuid = ? AND anchor_msg_id IS NULL
                """,
                [anchor_msg_id, *attachment_ids, user_uuid],
            )
            return cursor.rowcount

    def update_description(self, attachment_id: str, description: str) -> bool:
        now_ts = self._now_timestamp()
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE attachments SET description = ?, description_generated_at = ? WHERE attachment_id = ?",
                (description, now_ts, attachment_id),
            )
            return cursor.rowcount > 0

    def delete(self, attachment_id: str, user_uuid: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM attachments WHERE attachment_id = ? AND user_uuid = ?",
                (attachment_id, user_uuid),
            )
            return cursor.rowcount > 0
```

在 `DatabaseFacade.__init__` 中，`self.community_skills = CommunitySkillsFacade(self)` 之后添加：

```python
self.attachments = AttachmentsFacade(self)
```

在 `ModelConfigsFacade._COLUMNS` 改为包含两个新字段：

```python
_COLUMNS = (
    "config_id, user_uuid, config_name, api_key, base_url, model_name, "
    "temperature, max_tokens, is_active, supports_vision, is_vision_assistant, created_at, updated_at"
)
```

`ModelConfigsFacade.create` 新增两个参数（在 `is_active` 之后）：

```python
supports_vision: bool = False,
is_vision_assistant: bool = False,
```

对应 INSERT 语句改为包含这两个字段（在 `is_active` 之后加两个占位符）：

```python
cursor.execute(
    """
    INSERT INTO user_model_configs
        (config_id, user_uuid, config_name, api_key, base_url, model_name,
         user_instruction, temperature, max_tokens, is_active,
         supports_vision, is_vision_assistant, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        config_id, user_uuid, config_name, api_key, base_url, model_name,
        temperature, max_tokens,
        1 if is_active else 0,
        1 if supports_vision else 0,
        1 if is_vision_assistant else 0,
        now_ts, now_ts,
    ),
)
```

在 `setup_database` 的迁移段末尾（`self._migrate_legacy_community_skill_bodies` 之前）添加：

```python
# attachments 表
cursor.execute("""
    CREATE TABLE IF NOT EXISTS attachments (
        attachment_id TEXT PRIMARY KEY,
        sid TEXT NOT NULL REFERENCES sessions(sid) ON DELETE CASCADE,
        user_uuid TEXT NOT NULL,
        anchor_msg_id TEXT,
        original_filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        description TEXT,
        description_generated_at REAL,
        created_at REAL NOT NULL
    )
""")
cursor.execute(
    "CREATE INDEX IF NOT EXISTS idx_attachments_sid ON attachments(sid)"
)
# user_model_configs 视觉字段迁移
cursor.execute("PRAGMA table_info(user_model_configs)")
umc_cols = {row["name"] for row in cursor.fetchall()}
if "supports_vision" not in umc_cols:
    cursor.execute(
        "ALTER TABLE user_model_configs ADD COLUMN supports_vision INTEGER NOT NULL DEFAULT 0"
    )
if "is_vision_assistant" not in umc_cols:
    cursor.execute(
        "ALTER TABLE user_model_configs ADD COLUMN is_vision_assistant INTEGER NOT NULL DEFAULT 0"
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_attachments_db.py -v
```

期望：8 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/db.py tests/test_attachments_db.py
git commit -m "feat: 新增 attachments 表和 AttachmentsFacade，扩展 user_model_configs 视觉字段"
```

---

## Task 2: 配置层 — 视觉模型环境变量与辅助模型选取

**Files:**
- Modify: `backend/config/model.py`

---

- [ ] **Step 1: 添加视觉模型配置常量和辅助模型选取函数**

在 `backend/config/model.py` 中，在 `TEST_CONNECTION_TIMEOUT = 15` 之后添加：

```python
# ── 视觉模型配置 ──

VISION_MODEL_API_KEY = os.getenv("VISION_MODEL_API_KEY", "")
VISION_MODEL_BASE_URL = os.getenv("VISION_MODEL_BASE_URL", "")
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "")

# 逗号分隔的已知多模态模型名关键词（大小写不敏感的子串匹配）
# 示例：VISION_MODEL_WHITELIST=gpt-4o,gemini,claude-3
_VISION_WHITELIST_RAW = os.getenv("VISION_MODEL_WHITELIST", "")
VISION_MODEL_WHITELIST: list[str] = [
    kw.strip().lower()
    for kw in _VISION_WHITELIST_RAW.split(",")
    if kw.strip()
]


def model_name_is_vision(model_name: str) -> bool:
    """判断模型名是否命中视觉白名单（大小写不敏感子串匹配）。"""
    lower = model_name.lower()
    return any(kw in lower for kw in VISION_MODEL_WHITELIST)


def active_model_supports_vision(db, user_uuid: str) -> bool:
    """判断当前用户激活的模型配置是否支持视觉。

    优先级：
    1. 激活配置的 model_name 命中白名单
    2. 激活配置的 supports_vision 字段为 True
    3. 否则返回 False
    """
    config = db.model_configs.get_active_for_user(user_uuid)
    if config is None:
        return bool(VISION_MODEL_NAME) and model_name_is_vision(VISION_MODEL_NAME)
    model_name = config.get("model_name", "")
    if model_name and model_name_is_vision(model_name):
        return True
    return bool(config.get("supports_vision"))


def get_vision_assistant_provider(db, user_uuid: str) -> "OpenAIChatModel":
    """选取视觉辅助模型，按优先级：
    1. 用户配置中 is_vision_assistant=True 的配置
    2. 用户配置中 supports_vision=True 的任意一条（取第一条）
    3. 系统 env 默认视觉模型（VISION_MODEL_*）
    4. 抛出 RuntimeError
    """
    configs = db.model_configs.list_by_user(user_uuid)

    for c in configs:
        if c.get("is_vision_assistant"):
            return GetProvider(
                api_key=c.get("api_key") or None,
                base_url=c.get("base_url") or None,
                model_name=c.get("model_name") or None,
            )
    for c in configs:
        if c.get("supports_vision") or model_name_is_vision(c.get("model_name", "")):
            return GetProvider(
                api_key=c.get("api_key") or None,
                base_url=c.get("base_url") or None,
                model_name=c.get("model_name") or None,
            )
    if VISION_MODEL_NAME:
        return GetProvider(
            api_key=VISION_MODEL_API_KEY or None,
            base_url=VISION_MODEL_BASE_URL or None,
            model_name=VISION_MODEL_NAME,
        )

    raise RuntimeError(
        "没有可用的视觉辅助模型。请在用户设置中配置支持视觉的模型，"
        "或在环境变量中设置 VISION_MODEL_NAME。"
    )
```

- [ ] **Step 2: 确认导入无误**

```bash
cd /home/seeck/Projects/Teachi
uv run python -c "from backend.config.model import active_model_supports_vision, get_vision_assistant_provider, VISION_MODEL_WHITELIST; print('OK')"
```

期望：输出 `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/config/model.py
git commit -m "feat: 新增视觉模型环境变量和辅助模型选取逻辑"
```

---

## Task 3: API 层 — 附件上传/查询/删除接口 + 状态机扩展

**Files:**
- Modify: `backend/file.py`
- Modify: `backend/context.py`
- Modify: `backend/loop.py`
- Modify: `backend/data.py`
- Create: `tests/test_attachments_api.py`

---

- [ ] **Step 1: 在 `backend/file.py` 新增 `SessionFile` 类**

在 `UserFile` 类之后添加：

```python
class SessionFile(FileBase):
    """
    会话文件子类，限制在 data/{user_uuid}/{pid}/{sid}/。
    用于存储会话级附件（图片等）。
    """
    def __init__(self, sid: str, pid: str, user_uuid: str, db_facade):
        session = db_facade.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
        if not session:
            raise PermissionError(
                f"Access Denied: Session {sid} does not belong to user {user_uuid}"
            )
        if session["pid"] != pid:
            raise PermissionError(
                f"Access Denied: Session {sid} does not belong to project {pid}"
            )
        session_path = BASE_DIR / "data" / user_uuid / pid / sid
        super().__init__(session_path)
```

- [ ] **Step 2: 在 `backend/context.py` 的 `LoopContext` 新增字段**

在 `anchor_msg_id` 字段之后添加：

```python
# SEND: 前端传入的本轮附件 ID 列表，save_node 执行后写入 anchor_msg_id。
attachment_ids: list[str] | None = None
```

- [ ] **Step 3: 在 `backend/loop.py` 的 `ChatRequest` 新增字段**

在 `allowed_tools` 字段之后添加：

```python
attachment_ids: list[str] | None = Field(
    default=None,
    description="本轮附件 ID 列表，save_node 执行后写入 anchor_msg_id"
)
```

在 `chat_loop` 路由函数中创建 `LoopContext` 时添加：

```python
attachment_ids=payload.attachment_ids,
```

- [ ] **Step 4: 在 `backend/data.py` 新增三个附件路由**

首先确保顶部导入（补充缺失的）：

```python
import uuid as _uuid
from pathlib import Path
from fastapi import UploadFile, File as FastAPIFile
```

然后在文件末尾（或现有会话路由之后）添加以下常量和路由函数：

```python
# ── 附件接口 ──────────────────────────────────────────────

ALLOWED_IMAGE_MIME_TYPES: set[str] = {
    "image/jpeg", "image/png", "image/webp", "image/gif"
}
ATTACHMENT_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_MAGIC_BYTES: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG",
    "image/webp": b"RIFF",
    "image/gif": b"GIF",
}


def _check_magic_bytes(data: bytes, mime_type: str) -> bool:
    magic = _MAGIC_BYTES.get(mime_type)
    if magic is None:
        return False
    return data[:len(magic)] == magic


@router.post("/sessions/{sid}/attachments", status_code=201)
async def upload_attachment(
    sid: str,
    file: UploadFile = FastAPIFile(...),
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """上传图片附件，绑定到会话，anchor_msg_id 在发消息后由 save_node 写入。"""
    from backend.config import BASE_DIR

    user_uuid: str = current_user["uuid"]
    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )

    mime_type = file.content_type or ""
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": f"不支持的文件类型：{mime_type}"},
        )

    data = await file.read(ATTACHMENT_MAX_SIZE_BYTES + 1)
    if len(data) > ATTACHMENT_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "FILE_TOO_LARGE", "message": "文件超过 10MB 限制"},
        )

    if not _check_magic_bytes(data, mime_type):
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": "文件内容与声明的类型不符"},
        )

    pid = session["pid"]
    attachment_id = str(_uuid.uuid4())
    ext = _MIME_TO_EXT.get(mime_type, "")

    try:
        session_dir = BASE_DIR / "data" / user_uuid / pid / sid / "attachments"
        session_dir.mkdir(parents=True, exist_ok=True)
        file_path = session_dir / f"{attachment_id}{ext}"
        file_path.write_bytes(data)
        abs_file_path = str(file_path.relative_to(BASE_DIR))
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "STORAGE_ERROR", "message": str(e)})

    att = db.attachments.create(
        sid=sid,
        user_uuid=user_uuid,
        original_filename=file.filename or f"attachment{ext}",
        file_path=abs_file_path,
        mime_type=mime_type,
    )

    return {
        "attachment_id": att["attachment_id"],
        "original_filename": att["original_filename"],
        "mime_type": att["mime_type"],
        "created_at": att["created_at"],
    }


@router.get("/sessions/{sid}/attachments")
async def list_attachments(
    sid: str,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """列出会话所有附件。"""
    user_uuid: str = current_user["uuid"]
    session = db.sessions.get_for_user(sid=sid, user_uuid=user_uuid)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"},
        )
    attachments = db.attachments.list_by_session(sid, user_uuid)
    return {
        "attachments": [
            {
                "attachment_id": a["attachment_id"],
                "anchor_msg_id": a["anchor_msg_id"],
                "original_filename": a["original_filename"],
                "mime_type": a["mime_type"],
                "has_description": a["description"] is not None,
                "created_at": a["created_at"],
            }
            for a in attachments
        ]
    }


@router.delete("/sessions/{sid}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    sid: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    """删除附件记录及文件实体。"""
    from backend.config import BASE_DIR

    user_uuid: str = current_user["uuid"]
    att = db.attachments.get_for_user(attachment_id, user_uuid)
    if att is None or att["sid"] != sid:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Attachment not found"},
        )

    file_path = BASE_DIR / att["file_path"]
    if file_path.is_file():
        file_path.unlink(missing_ok=True)

    db.attachments.delete(attachment_id, user_uuid)
    return None
```

- [ ] **Step 5: 写 API 集成测试**

新建 `tests/test_attachments_api.py`。实现前需先确认测试中用到的 `get_db` 依赖的导入路径（在项目中运行 `grep -r "def get_db" backend/` 确认），以及 `/auth/register`、`/auth/login`、`/auth/me`、`/users/{uid}/projects`、`/projects/{pid}/sessions` 等端点的实际路径。参考以下框架并适配：

```python
import io
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import DatabaseFacade


def _make_jpeg() -> bytes:
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )


# Fixtures: db, client (with dependency override), auth_headers, session_ids
# 参考现有 tests/ 目录下的测试文件中的 fixture 写法来适配

def test_upload_attachment_success(client, auth_headers, session_ids):
    pid, sid = session_ids
    resp = client.post(
        f"/sessions/{sid}/attachments",
        files={"file": ("photo.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["attachment_id"]
    assert resp.json()["mime_type"] == "image/jpeg"


def test_upload_attachment_wrong_type(client, auth_headers, session_ids):
    pid, sid = session_ids
    resp = client.post(
        f"/sessions/{sid}/attachments",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_upload_attachment_magic_bytes_mismatch(client, auth_headers, session_ids):
    pid, sid = session_ids
    resp = client.post(
        f"/sessions/{sid}/attachments",
        files={"file": ("fake.jpg", io.BytesIO(b"notajpeg"), "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_list_attachments(client, auth_headers, session_ids):
    pid, sid = session_ids
    client.post(
        f"/sessions/{sid}/attachments",
        files={"file": ("a.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
        headers=auth_headers,
    )
    resp = client.get(f"/sessions/{sid}/attachments", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["attachments"]) == 1
    assert resp.json()["attachments"][0]["has_description"] is False


def test_delete_attachment(client, auth_headers, session_ids):
    pid, sid = session_ids
    att_id = client.post(
        f"/sessions/{sid}/attachments",
        files={"file": ("b.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
        headers=auth_headers,
    ).json()["attachment_id"]
    assert client.delete(f"/sessions/{sid}/attachments/{att_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/sessions/{sid}/attachments", headers=auth_headers).json()["attachments"] == []
```

- [ ] **Step 6: 运行测试**

```bash
uv run pytest tests/test_attachments_api.py -v
```

期望：5 个测试全部 PASS

- [ ] **Step 7: 提交**

```bash
git add backend/file.py backend/context.py backend/loop.py backend/data.py tests/test_attachments_api.py
git commit -m "feat: 新增附件上传/查询/删除 API，扩展 LoopContext 和 ChatRequest"
```

---

## Task 4: 工具层 + 状态机扩展

**Files:**
- Modify: `backend/tool.py`
- Modify: `backend/node.py`
- Create: `tests/test_view_attachment_tool.py`

---

- [ ] **Step 1: 写失败测试**

新建 `tests/test_view_attachment_tool.py`：

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_ctx(user_uuid="user-1", pid="pid-1", sid="sid-1"):
    from backend.context import ChatDeps, ToolMode
    deps = ChatDeps(
        user_uuid=user_uuid,
        pid=pid,
        sid=sid,
        allowed_tools=None,
        db=MagicMock(),
        tool_mode=ToolMode.ON,
    )
    ctx = MagicMock()
    ctx.deps = deps
    return ctx, deps


@pytest.mark.asyncio
async def test_view_attachment_not_found():
    from backend.tool import view_attachment
    ctx, deps = _make_ctx()
    deps.db.attachments.get_for_user.return_value = None
    result = await view_attachment(ctx, "nonexistent-id")
    assert "错误" in result.return_value


@pytest.mark.asyncio
async def test_view_attachment_uses_cached_description():
    from backend.tool import view_attachment
    ctx, deps = _make_ctx()
    deps.db.attachments.get_for_user.return_value = {
        "attachment_id": "att-1",
        "sid": "sid-1",
        "user_uuid": "user-1",
        "original_filename": "cat.jpg",
        "file_path": "data/u/p/s/attachments/att-1.jpg",
        "mime_type": "image/jpeg",
        "description": "一只白猫坐在窗台上，背景是蓝天。",
        "description_generated_at": 1748736000.0,
    }
    with patch("backend.config.model.active_model_supports_vision", return_value=False):
        result = await view_attachment(ctx, "att-1")
    assert result.return_value == "一只白猫坐在窗台上，背景是蓝天。"
    deps.db.attachments.update_description.assert_not_called()


@pytest.mark.asyncio
async def test_view_attachment_generates_description_when_missing():
    from backend.tool import view_attachment
    ctx, deps = _make_ctx()
    deps.db.attachments.get_for_user.return_value = {
        "attachment_id": "att-2",
        "sid": "sid-1",
        "user_uuid": "user-1",
        "original_filename": "chart.png",
        "file_path": "data/u/p/s/attachments/att-2.png",
        "mime_type": "image/png",
        "description": None,
        "description_generated_at": None,
    }
    generated_desc = "折线图，X 轴为月份（1-12），Y 轴为销售额（万元）。"
    with (
        patch("backend.config.model.active_model_supports_vision", return_value=False),
        patch("backend.tool._generate_description", new=AsyncMock(return_value=generated_desc)),
    ):
        result = await view_attachment(ctx, "att-2")
    assert result.return_value == generated_desc


@pytest.mark.asyncio
async def test_view_attachment_returns_binary_for_vision_model(tmp_path):
    from backend.tool import view_attachment
    from pydantic_ai import BinaryContent
    ctx, deps = _make_ctx()

    fake_image = b"\xff\xd8\xff" + b"\x00" * 100
    img_path = tmp_path / "att-3.jpg"
    img_path.write_bytes(fake_image)

    deps.db.attachments.get_for_user.return_value = {
        "attachment_id": "att-3",
        "sid": "sid-1",
        "user_uuid": "user-1",
        "original_filename": "photo.jpg",
        "file_path": str(img_path),
        "mime_type": "image/jpeg",
        "description": "照片内容叙述。",
        "description_generated_at": 1748736000.0,
    }
    with patch("backend.config.model.active_model_supports_vision", return_value=True):
        result = await view_attachment(ctx, "att-3")

    assert result.return_value == "照片内容叙述。"
    assert result.content is not None
    assert any(isinstance(c, BinaryContent) for c in result.content)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_view_attachment_tool.py -v
```

期望：FAILED — `view_attachment` 未定义

- [ ] **Step 3: 在 `backend/tool.py` 实现工具**

在 `delete_skill` 函数之后添加：

```python
# ── 视觉附件工具 ──────────────────────────────────────────────


async def _generate_description(attachment: dict, db, user_uuid: str) -> str | None:
    """调用视觉辅助模型生成图片精确内容叙述，成功后写入数据库缓存。"""
    from backend.config.model import get_vision_assistant_provider
    from backend.config import BASE_DIR
    from pydantic_ai import Agent, BinaryContent

    try:
        vision_model = get_vision_assistant_provider(db, user_uuid)
    except RuntimeError:
        return None

    file_path_str: str = attachment["file_path"]
    from pathlib import Path
    file_path = (
        Path(file_path_str)
        if Path(file_path_str).is_absolute()
        else BASE_DIR / file_path_str
    )
    if not file_path.is_file():
        return None

    image_bytes = file_path.read_bytes()
    mime_type: str = attachment["mime_type"]

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
    except Exception:
        return None

    db.attachments.update_description(attachment["attachment_id"], description)
    return description


@register_tool
async def view_attachment(
    ctx: RunContext[Any],
    attachment_id: str,
) -> Any:
    """读取附件内容。当用户消息与上传的附件相关时，必须先调用此工具读取附件，再回答用户。

    Args:
        attachment_id: 附件 ID，来自会话系统提示词中列出的附件列表。

    Returns:
        ToolReturn：return_value 为图片精确内容叙述文字；
        若主模型支持视觉，content 中额外包含原始图片 BinaryContent。
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

    attachment = db.attachments.get_for_user(attachment_id, user_uuid)
    if attachment is None:
        return ToolReturn(return_value="错误：附件不存在或无权访问。")

    description: str | None = attachment.get("description")
    if description is None:
        description = await _generate_description(attachment, db, user_uuid)
        if description is None:
            return ToolReturn(return_value="错误：无法生成图片内容叙述，请检查视觉模型配置。")

    if active_model_supports_vision(db, user_uuid):
        file_path_str: str = attachment["file_path"]
        file_path = (
            Path(file_path_str)
            if Path(file_path_str).is_absolute()
            else BASE_DIR / file_path_str
        )
        if file_path.is_file():
            image_bytes = file_path.read_bytes()
            return ToolReturn(
                return_value=description,
                content=[description, BinaryContent(data=image_bytes, media_type=attachment["mime_type"])],
            )

    return ToolReturn(return_value=description)
```

- [ ] **Step 4: 在 `backend/node.py` 读取 `node.py` 找到 `validate_node` 和 `save_node` 和 `build_model_node` 的具体位置，然后做以下三处修改**

首先阅读 `backend/node.py` 确认这三个节点函数的签名和内部结构，再做修改。

**validate_node**：在 SEND 动作的基础校验（`if not ctx.pid` 等）之后，添加附件归属校验：

```python
if ctx.attachment_ids:
    for att_id in ctx.attachment_ids:
        att = db.attachments.get_for_user(att_id, ctx.user_uuid)
        if att is None:
            ctx.error = f"Attachment {att_id} not found or does not belong to user"
            ctx.error_code = "RESOURCE_NOT_FOUND"
            return NodeOutput(transition=NodeName.STREAM_ERROR)
        if att["sid"] != ctx.sid:
            ctx.error = f"Attachment {att_id} does not belong to session {ctx.sid}"
            ctx.error_code = "FORBIDDEN"
            return NodeOutput(transition=NodeName.STREAM_ERROR)
        if att["anchor_msg_id"] is not None:
            ctx.error = f"Attachment {att_id} is already bound to another turn"
            ctx.error_code = "BAD_REQUEST"
            return NodeOutput(transition=NodeName.STREAM_ERROR)
```

**save_node**：在 `db.sessions.touch_timestamp(sid=ctx.sid)` 调用之前（或之后均可，无顺序依赖），添加：

```python
if ctx.attachment_ids and ctx.anchor_msg_id:
    db.attachments.bind_anchor(
        attachment_ids=ctx.attachment_ids,
        anchor_msg_id=ctx.anchor_msg_id,
        user_uuid=ctx.user_uuid,
    )
```

**build_model_node**：在 `ctx.agent = GetAgent(...)` 之后，找到现有的 `ctx.agent.instructions(...)` 调用，将其替换为：

```python
session_attachments = db.attachments.list_by_session(ctx.sid, ctx.user_uuid)
attachment_constraint = ""
if session_attachments:
    lines = [
        f"- {a['original_filename']} (attachment_id: {a['attachment_id']})"
        for a in session_attachments
    ]
    attachment_constraint = (
        "\n\n用户在本会话中上传了以下附件：\n"
        + "\n".join(lines)
        + "\n\n当用户的消息与上述附件相关时，"
        "你必须先调用 view_attachment(attachment_id=...) 工具读取附件内容，"
        "再回答用户。不得跳过此步骤。"
    )

base_prompt_fn = load_prompt("init.md", "harness.md", "text_output.md")
if attachment_constraint:
    _constraint_snapshot = attachment_constraint
    ctx.agent.instructions(lambda: base_prompt_fn() + _constraint_snapshot)
else:
    ctx.agent.instructions(base_prompt_fn)
```

- [ ] **Step 5: 运行工具测试**

```bash
uv run pytest tests/test_view_attachment_tool.py -v
```

期望：4 个测试全部 PASS

- [ ] **Step 6: 运行全量测试，确认无回归**

```bash
uv run pytest -v
```

- [ ] **Step 7: 提交**

```bash
git add backend/tool.py backend/node.py tests/test_view_attachment_tool.py
git commit -m "feat: 新增 view_attachment 工具和状态机约束注入"
```

---

## Task 5: 前端层 — 附件 UI + api.ts + AIConfigDialog 扩展

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/views/ChatView.vue`
- Modify: `frontend/src/components/AIConfigDialog.vue`

> 本任务为前端任务，需要先阅读这三个文件的当前内容，理解项目现有的 `apiFetch` 封装、发送消息的函数签名、表单结构，再按以下规格修改。

---

- [ ] **Step 1: 阅读前端文件，了解现有结构**

阅读以下文件（使用 view_file 工具）：
- `frontend/src/api.ts`（重点：`apiFetch` 封装、现有方法签名）
- `frontend/src/views/ChatView.vue`（重点：Composer 区域、发送函数、`isStreaming` 状态）
- `frontend/src/components/AIConfigDialog.vue`（重点：表单结构、`form` reactive 对象）

- [ ] **Step 2: 在 `frontend/src/api.ts` 新增三个附件方法**

添加 TypeScript 接口和函数：

```typescript
// ── 附件 API ──

export interface AttachmentUploadResult {
  attachment_id: string
  original_filename: string
  mime_type: string
  created_at: number
}

export interface AttachmentItem {
  attachment_id: string
  anchor_msg_id: string | null
  original_filename: string
  mime_type: string
  has_description: boolean
  created_at: number
}

// 上传时不设 Content-Type 头，让浏览器自动设置 multipart boundary
export async function uploadAttachment(
  sid: string,
  file: File,
): Promise<AttachmentUploadResult> {
  const form = new FormData()
  form.append('file', file)
  // 注意：根据 apiFetch 的实现，需要确保 multipart 请求不手动设 Content-Type
  // 如果 apiFetch 自动加 application/json，需要传 body: form 时跳过
  const token = getToken()  // 使用项目现有的 token 获取方式
  const resp = await fetch(`${API_BASE}/sessions/${sid}/attachments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!resp.ok) throw new Error(await resp.text())
  return resp.json()
}

export async function listAttachments(sid: string): Promise<AttachmentItem[]> {
  const data = await apiFetch<{ attachments: AttachmentItem[] }>(
    `/sessions/${sid}/attachments`,
  )
  return data.attachments
}

export async function deleteAttachment(sid: string, attachmentId: string): Promise<void> {
  await apiFetch<void>(`/sessions/${sid}/attachments/${attachmentId}`, {
    method: 'DELETE',
  })
}
```

> **注意：** `uploadAttachment` 中使用直接 `fetch` 而非 `apiFetch`，是因为 `apiFetch` 通常会自动设置 `Content-Type: application/json`，会破坏 `multipart/form-data` 的 boundary。根据项目实际封装调整——如果 `apiFetch` 支持不设 Content-Type，则可以统一使用。

- [ ] **Step 3: 扩展 `ChatView.vue`**

在 `<script setup>` 中添加附件状态和处理函数（参考规格文件中的 TypeScript 代码），在模板中添加：
1. 隐藏的 `<input type="file" accept="image/*">` 元素（ref 为 `fileInputRef`）
2. 📎 按钮（点击触发 `fileInputRef.value?.click()`，`disabled` 状态与现有发送按钮一致）
3. 附件缩略图 chip 列表（在输入框上方，`v-if="pendingAttachments.length > 0"`）

在发送函数中，携带 `attachment_ids`，发送成功后清空 `pendingAttachments`。

- [ ] **Step 4: 扩展 `AIConfigDialog.vue`**

在表单的 `Temperature` / `Max Tokens` 字段之后添加：
1. `supports_vision` 复选框（标签：「此模型支持视觉（图片输入）」）
2. `is_vision_assistant` 复选框（标签：「设为视觉辅助模型（非视觉主模型时用于图片叙述）」）

在 `form` reactive 对象中新增这两个字段（默认 `false`），在创建/更新 API 调用时携带。

确认 `api.ts` 中 `createModelConfig` / `updateModelConfig` 的请求体包含这两个字段。

- [ ] **Step 5: 手动验证**

```bash
# 终端 1
cd /home/seeck/Projects/Teachi
uv run uvicorn backend.main:app --reload

# 终端 2
cd /home/seeck/Projects/Teachi/frontend
npm run dev
```

验证步骤：
1. 登录 → 创建项目 → 创建会话 → 进入聊天
2. 点击 📎 → 选图片 → 确认缩略图 chip 出现
3. 发消息 → 确认 SSE 中出现 `view_attachment` 工具调用事件
4. 确认回复包含对图片内容的叙述
5. Settings → 模型配置 → 确认「支持视觉」和「视觉辅助模型」复选框出现

- [ ] **Step 6: 提交**

```bash
cd /home/seeck/Projects/Teachi
git add frontend/src/api.ts frontend/src/views/ChatView.vue frontend/src/components/AIConfigDialog.vue
git commit -m "feat: 前端新增附件上传 UI、api.ts 附件方法、AIConfigDialog 视觉字段"
```
