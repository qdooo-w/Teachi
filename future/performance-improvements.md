# Teachi Backend 性能优化路线图

本文档基于对整个后端代码库的全面审查，按优先级列出可提升的性能点，涵盖异步/同步、数据库、并发、流式传输、AI 调用、文件 I/O、内存管理等维度。

---

## 目录

1. [事件循环阻塞（Critical）](#1-事件阻塞-critical)
2. [数据库连接与查询](#2-数据库连接与查询)
3. [AI 模型调用](#3-ai-模型调用)
4. [SSE 流式传输](#4-sse-流式传输)
5. [并发与锁机制](#5-并发与锁机制)
6. [文件 I/O](#6-文件-io)
7. [内存管理](#7-内存管理)
8. [启动与关闭](#8-启动与关闭)
9. [优化优先级矩阵](#9-优化优先级矩阵)

---

## 1. 事件循环阻塞（Critical）

### 问题

`chat_loop`（`loop.py:208`）是 `async def`，其依赖链 `get_current_user` → `db.users.get_by_uuid()` 和 `verify_nonce` → `db.nonces.use_nonce()` 均为同步 SQLite 调用。FastAPI 对 `async def` 路由**不会**放入线程池，同步 DB 调用直接阻塞事件循环。

同理，`node.py` 中的 `validate_node`（行75）、`load_history_node`（行158）、`save_node`（行281）都是 `async def` 函数，内部却执行同步 SQLite 操作。

### 优化方案

**方案 A：将同步 DB 调用包装为异步（推荐）**

```python
import asyncio

async def get_current_user_uuid(token: str = Depends(oauth2_scheme)) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _verify_token_sync, token)
```

- 改动范围小，对现有代码侵入低
- 利用 FastAPI 默认线程池（`run_in_executor(None, ...)` 使用默认 ThreadPoolExecutor）

**方案 B：将 chat_loop 改为同步 def**

```python
@router.post("/loop/{sid}")
def chat_loop(...):  # 不再是 async def
    ...
```

- FastAPI 会自动在线程池中运行，同步 DB 调用不再阻塞事件循环
- 但会失去在路由内 `await` 异步操作的能力（如 SSE 流式生成器需要 async）

**方案 C：换用 aiosqlite**

```python
import aiosqlite

async def get_user(uuid: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE uuid=?", (uuid,)) as cursor:
            return await cursor.fetchone()
```

- 真正的异步 I/O，不占线程池
- 改动范围大，需要重写 DatabaseFacade

**推荐**：方案 A 作为短期修复（改动最小），方案 C 作为长期目标。

---

## 2. 数据库连接与查询

### 2.1 无连接池：每次查询新建连接

**位置**：`db.py:661-677`（`db_cursor` 方法）

当前 `db_cursor()` 每次调用 `get_connection()` 创建新连接，用完立即关闭。一次聊天请求涉及 10+ 次连接开闭。

**优化方案**：

```python
class DatabaseFacade:
    _conn: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=OFF;")
        return self._conn
```

- 进程生命周期内复用单个连接
- SQLite 是进程级锁，单连接已足够
- 若后续需要并发读，可引入 `aiosqlite` 的连接池

### 2.2 多处重复实例化 DatabaseFacade

**位置**：`main.py:12`、`auth.py:29`、`data.py:24`、`node.py:75/158/281`、`file.py:142`

每个模块甚至每个请求都 `new DatabaseFacade()`，无法共享连接。

**优化方案**：通过 FastAPI 依赖注入共享单例

```python
# db.py
_db_instance: Optional[DatabaseFacade] = None

def get_db() -> DatabaseFacade:
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseFacade(DATABASE_PATH)
    return _db_instance

# 路由中使用
def get_current_user(db: DatabaseFacade = Depends(get_db)):
    ...
```

### 2.3 N+1 查询：save_agent_messages

**位置**：`db.py:521-588`

`save_agent_messages` 对每条消息执行 3 次查询（权限检查 + 插入 + 重读），N 条消息 = 3N 次数据库往返。

**优化方案**：使用 `executemany` 批量插入 + 事务合并

```python
def save_agent_messages_batch(self, messages: list[dict]):
    with self.db_cursor() as cur:
        # 一次性权限检查
        cur.execute("SELECT uuid FROM sessions WHERE sid=?", (messages[0]["sid"],))
        if not cur.fetchone():
            raise PermissionError(...)

        # 批量插入
        cur.executemany(
            "INSERT INTO messages (sid, role, content, ...) VALUES (?, ?, ?, ...)",
            [(m["sid"], m["role"], m["content"], ...) for m in messages]
        )
        # 不需要重读，直接用 lastrowid 构造返回值
```

### 2.4 缺失索引

**位置**：`db.py:689-737`（`setup_database`）

当前仅 `nonces(timestamp)` 有索引。高频查询缺少索引：

```sql
-- 建议添加
CREATE INDEX IF NOT EXISTS idx_messages_sid ON messages(sid);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_msg_id);
CREATE INDEX IF NOT EXISTS idx_messages_sid_latest ON messages(sid, is_latest);
CREATE INDEX IF NOT EXISTS idx_messages_sid_ts ON messages(sid, timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_pid ON sessions(pid);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_uuid);
```

### 2.5 插入后重读（INSERT + SELECT）

**位置**：`UsersFacade.create`（行38-52）、`ProjectsFacade.create`（行80-94）、`SessionsFacade.create`（行143-157）、`MessagesFacade.create`（行222-245）

所有 `create` 方法在 INSERT 后立即 SELECT 重读整行，完全多余。

**优化方案**：用 `RETURNING` 子句（SQLite 3.35+）或直接用 `cursor.lastrowid` 构造返回值

```python
def create(self, ...) -> dict:
    with self.db_cursor() as cur:
        cur.execute("INSERT INTO ... VALUES (...) RETURNING *", (...))
        return dict(zip(COLUMN_NAMES, cur.fetchone()))
```

---

## 3. AI 模型调用

### 3.1 每次请求新建 Agent 实例（低优先级）

**位置**：`config.py:47-57`、`node.py:214`

`create_chat_agent()` 每次调用都新建 Agent 实例。经实测，Pydantic AI 内部的 `httpx.AsyncClient` 已通过 `@functools.cache` 按 provider 名缓存，**HTTP 连接和 TLS 握手是复用的**。Agent 实例本身仅存储轻量引用（model、instructions、tools 列表），每个实例仅几 KB。

实际影响：每请求的 `build_tools()` Tool 包装 + 对象创建开销，非关键路径。

**优化方案**：模块级缓存 Agent 单例（最佳实践，改动极小）

```python
# config.py
_agent: Agent | None = None

def get_chat_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(get_chat_model(), instructions="你是一个智能助手", deps_type=ChatDeps)
    return _agent
```

### 3.2 模型调用无超时

**位置**：`node.py:231-265`

`agent.run_stream_events()` 无超时配置。上游 API 挂起时，请求将无限阻塞。

**优化方案**：

```python
try:
    async with asyncio.timeout(120):  # 2 分钟超时
        async with agent.run_stream_events(...) as stream:
            ...
except asyncio.TimeoutError:
    # 发送错误事件给客户端
    await _emit(ctx, {"type": "error", "content": "Model response timeout"})
```

### 3.3 重试策略不区分异常类型

**位置**：`node.py:270-273`

当前对所有异常都重试，包括 400 Bad Request 等不应重试的错误。

**优化方案**：

```python
import httpx

RETRYABLE_ERRORS = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)

try:
    ...
except RETRYABLE_ERRORS as e:
    if ctx.retries < MAX_RETRIES:
        ctx.retries += 1
        return "CALL_MODEL"  # 重试
    raise
except Exception:
    raise  # 不重试
```

---

## 4. SSE 流式传输

### 4.1 缺少反向代理穿透头

**位置**：`loop.py:230`（`StreamingResponse`）

nginx 等反向代理默认会缓冲响应，导致 SSE 流式传输失效。

**优化方案**：

```python
return StreamingResponse(
    stream_response(ctx),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # nginx
        "Connection": "keep-alive",
    },
)
```

### 4.2 SSE 队列无背压控制

**位置**：`node.py:60`（`_emit` 函数）

`asyncio.Queue()` 无 `maxsize`，客户端读取慢时队列无限增长。

**优化方案**：

```python
ctx.sse_queue = asyncio.Queue(maxsize=100)  # 限制队列大小
```

当队列满时 `put()` 会自动阻塞，形成背压。

### 4.3 15 秒轮询间隔过长

**位置**：`loop.py:169`

客户端在模型无输出时最多等待 15 秒才收到完成帧。

**优化方案**：发送心跳事件

```python
async def stream_response(ctx):
    while True:
        try:
            event = await asyncio.wait_for(ctx.sse_queue.get(), timeout=5)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            # 发送心跳保持连接
            yield ": heartbeat\n\n"
```

---

## 5. 并发与锁机制

### 5.1 _user_locks 字典条目不清理（低优先级）

**位置**：`loop.py:38-46`

锁本身的 acquire/release 是正常的，但 `get_user_lock()` 只往字典里加条目，从不删除。每个 `asyncio.Lock` 仅占几百字节，万级用户也就几 MB，实际影响极小。

**可选优化**：使用 `WeakValueDictionary` 自动回收无引用的锁，或在用户会话结束时清理条目。非必要不改。

### 5.2 潜在的锁双重释放

**位置**：`node.py:143`（`stop_node`）

`stop_node` 中有独立的 `lock.release()` 调用，若图引擎后续也执行 `release_lock_node`，会导致双重释放。

**优化方案**：统一在 `release_lock_node` 中释放，`stop_node` 中移除 `lock.release()`

```python
async def stop_node(ctx: LoopContext) -> str:
    await _emit(ctx, {"type": "stopped"})
    return "STOP"  # 图引擎路由到 RELEASE_LOCK，统一释放
```

### 5.3 无并发执行

当前所有工作都是顺序执行，没有利用 `asyncio.gather` 并行化独立任务。

**可并行化的场景**：
- 多条消息的批量插入
- 文件操作 + 数据库操作
- 多个独立的工具调用

---

## 6. 文件 I/O

### 6.1 同步阻塞文件操作

**位置**：`file.py:35`（`write_text`）、`file.py:77`（`read_text`）、`file.py:65`（`rmtree`）

所有文件操作都是同步阻塞的，若 Pydantic AI 在事件循环线程中执行工具，会阻塞事件循环。

**优化方案**：使用 `aiofiles` 或 `run_in_executor`

```python
import aiofiles

async def read_file_async(self, path: str) -> str:
    target = self._safe_path(path)
    async with aiofiles.open(target, mode="r", encoding="utf-8") as f:
        return await f.read()
```

### 6.2 无文件大小限制

**位置**：`file.py:30-38`、`file.py:71-79`

`read_file` 将整个文件读入内存，无大小检查，可能导致 OOM。

**优化方案**：

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def read_file(self, path: str) -> str:
    target = self._safe_path(path)
    if target.stat().st_size > MAX_FILE_SIZE:
        raise FileError(f"File too large: {target.stat().st_size} bytes (max {MAX_FILE_SIZE})")
    return target.read_text(encoding="utf-8")
```

### 6.3 每次文件操作新建 DatabaseFacade

**位置**：`file.py:141-142`

`filesystem_tool_handler` 每次调用都新建 `DatabaseFacade`。

**优化方案**：通过依赖注入传入共享的 db 实例（参见 2.2）。

---

## 7. 内存管理

### 7.1 会话历史全量加载

**位置**：`node.py:158-174`

`load_history_node` 加载整个会话的所有消息（含 `raw_json` 序列化数据），长会话可能占用大量内存。

**优化方案**：限制加载最近 N 条消息

```python
MAX_HISTORY_MESSAGES = 50

raw_messages = db.messages.list_latest_by_session_for_user(
    sid=ctx.sid, limit=MAX_HISTORY_MESSAGES
)
```

### 7.2 消息去重的 O(N*M) 复杂度

**位置**：`node.py:284-287`

```python
new_messages = [m for m in ctx.messages if m not in ctx.history_messages]
```

对 `ModelMessage` 对象做 `not in` 列表比较，涉及深度对象相等性判断，复杂度 O(N*M)。

**优化方案**：用集合（set）做 O(1) 查找

```python
# 如果 ModelMessage 可哈希
history_set = set(ctx.history_messages)
new_messages = [m for m in ctx.messages if m not in history_set]

# 如果不可哈希，用 id 或 content hash 做 key
history_ids = {id(m) for m in ctx.history_messages}
new_messages = [m for m in ctx.messages if id(m) not in history_ids]
```

### 7.3 _running_tasks 异常泄漏

**位置**：`loop.py:39`

若 task 崩溃且未触发 `release_lock_node`，`_running_tasks` 中的引用会永久保留。

**优化方案**：添加 task 完成回调

```python
def _task_done_callback(user_uuid: str, task: asyncio.Task):
    _running_tasks.pop(user_uuid, None)
    if task.exception():
        _user_locks.get(user_uuid, asyncio.Lock()).release()

task = asyncio.create_task(run_loop(ctx))
task.add_done_callback(lambda t: _task_done_callback(ctx.user_uuid, t))
_running_tasks[ctx.user_uuid] = task
```

---

## 8. 启动与关闭

### 8.1 无关闭清理

**位置**：`main.py:15-19`

`lifespan` 的 `yield` 后无清理逻辑。

**优化方案**：

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    db.setup_database()
    yield
    # 清理
    for task in _running_tasks.values():
        task.cancel()
    _user_locks.clear()
    _running_tasks.clear()
```

### 8.2 模块级 DatabaseFacade 在 setup_database 之前创建

**位置**：`main.py:12`、`auth.py:29`、`data.py:24`

模块导入时就实例化 `DatabaseFacade`，但 `setup_database()` 在 lifespan 中才执行。

**优化方案**：延迟初始化（参见 2.2 的 `get_db()` 依赖注入方案）。

---

## 9. 优化优先级矩阵

| 优先级 | 问题 | 影响 | 改动量 | 方案 |
|--------|------|------|--------|------|
| P0 | 事件循环阻塞 | 高 | 中 | `run_in_executor` 或换 `aiosqlite` |
| P0 | 无连接池 | 高 | 小 | 单连接复用 |
| P0 | 缺失索引 | 高 | 小 | 添加 6 个索引 |
| P1 | N+1 查询 | 中 | 中 | `executemany` 批量操作 |
| P2 | Agent 每次新建 | 低 | 小 | 模块级缓存单例（HTTP 客户端已自动缓存） |
| P1 | 无模型调用超时 | 中 | 小 | `asyncio.timeout` |
| P1 | SSE 缺少代理头 | 中 | 小 | 添加 headers |
| P3 | _user_locks 条目不清理 | 极低 | 小 | WeakValueDictionary（非必要不改） |
| P2 | 消息去重 O(N*M) | 低 | 小 | 用 set 替代列表查找 |
| P2 | 文件操作阻塞 | 低 | 中 | aiofiles 或 run_in_executor |
| P2 | 无文件大小限制 | 低 | 小 | 添加 stat 检查 |
| P3 | 插入后重读 | 低 | 中 | RETURNING 子句 |
| P3 | 会话历史全量加载 | 低 | 小 | 添加 limit 参数 |
| P3 | 无关闭清理 | 低 | 小 | lifespan 清理逻辑 |
| P3 | 重试策略不区分 | 低 | 小 | 区分可重试异常 |

---

## 附录：异步改造路线图

### 阶段一：快速修复（1-2 天）

- [ ] 添加数据库索引
- [ ] SSE 添加 `Cache-Control` / `X-Accel-Buffering` 头
- [ ] `_user_locks` 改用 `WeakValueDictionary`
- [ ] Agent 实例缓存为单例
- [ ] 模型调用添加超时
- [ ] 文件大小限制

### 阶段二：连接优化（2-3 天）

- [ ] DatabaseFacade 单连接复用
- [ ] 依赖注入统一 db 实例
- [ ] `save_agent_messages` 批量插入
- [ ] 移除 INSERT 后的 SELECT 重读
- [ ] 消息去重改用 set

### 阶段三：异步化（3-5 天）

- [ ] 引入 `aiosqlite` 替换同步 sqlite3
- [ ] 文件操作换用 `aiofiles`
- [ ] `chat_loop` 依赖链异步化
- [ ] SSE 心跳机制

### 阶段四：高级优化（按需）

- [ ] 消息历史分页/截断
- [ ] `asyncio.gather` 并行化独立操作
- [ ] 关闭清理逻辑
- [ ] 重试策略细化
- [ ] 监控指标（请求延迟、DB 耗时、模型调用耗时）
