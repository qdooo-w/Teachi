# Teachi Backend 安全审计报告

基于对后端全部 Python 文件的全面审查，按严重程度分类列出安全问题及修复建议。

---

## 审计总结

| 严重程度 | 数量 | 说明 |
|----------|------|------|
| CRITICAL | 1 | 必须立即修复，可直接导致系统被攻破 |
| HIGH | 5 | 需尽快修复，存在被利用的现实路径 |
| MEDIUM | 11 | 应在上线前修复，降低攻击面 |
| LOW | 8 | 建议改进，实际利用难度较高 |

**正面发现**：
- SQL 查询全部使用参数化占位符（`?`），无注入风险
- 无 `os.system`、`subprocess`、`eval`、`exec` 等命令注入点
- 密码哈希使用 PBKDF2-HMAC-SHA256 + 120k 迭代 + `secrets` 生成盐，合理
- 密码比对使用 `hmac.compare_digest`，防时序攻击
- `.env` 已在 `.gitignore` 中，未泄露到 git 历史
- 请求体全部经过 Pydantic `BaseModel` 校验

---

## CRITICAL

### C1. JWT 密钥默认为空字符串 — 可伪造任意 Token

**位置**：`config.py:19`

```python
JWT_SECRET = os.getenv("JWT_SECRET", "")
```

**问题**：未设置环境变量时，JWT 使用空字符串签名。PyJWT 不拒绝空密钥，攻击者可随意伪造任意用户的 access token。

**修复**：启动时校验，空则拒绝启动

```python
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be set and at least 32 characters")
```

---

## HIGH

### H1. 无接口限流 — 登录端点可被暴力破解

**位置**：`auth.py` 全文、`main.py` 全文

**问题**：`/auth/login`、`/auth/register`、`/auth/refresh` 无任何限流。攻击者可无限次尝试密码。

**修复**：添加限流中间件（如 `slowapi`）或在反向代理层限流

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@router.post("/login")
@limiter.limit("5/minute")
async def login_user(request: Request, ...):
    ...
```

### H2. Refresh Token 无吊销机制 — 被盗后 7 天内可无限使用

**位置**：`auth.py:313-328`

**问题**：`/auth/refresh` 每次签发新 refresh token，但旧 token 不失效。代码注释已标注"后续处理旧 refresh token 的吊销"。被盗 token 在 7 天有效期内可持续使用。

**修复**：实现 token rotation + 数据库记录

```sql
-- 新增表
CREATE TABLE refresh_tokens (
    token_hash TEXT PRIMARY KEY,
    user_uuid TEXT NOT NULL,
    family TEXT NOT NULL,       -- token 家族，同一登录链
    expires_at INTEGER NOT NULL,
    revoked INTEGER DEFAULT 0
);
```

refresh 时：验证旧 token → 标记已撤销 → 签发新 token。若检测到已撤销的 token 被使用，撤销整个 family（检测到泄露）。

### H3. Cookie Secure 默认为 False — 明文传输 Refresh Token

**位置**：`auth.py:33`

```python
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "false").lower() == "true"
```

**问题**：生产环境若未设置该变量，refresh token cookie 通过 HTTP 明文传输，可被中间人截获。

**修复**：默认 `true`，仅开发环境显式关闭

```python
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "true").lower() == "true"
```

### H4. _safe_path 使用字符串前缀匹配 — 路径遍历防护不严谨

**位置**：`file.py:20-28`

```python
if not str(target_path).startswith(str(self.base_path)):
```

**问题**：字符串 `startswith` 在边界情况下不可靠。例如 `base_path="/data/abc"` 会匹配 `/data/abcdef/...`。虽然当前构造方式（`self.base_path / clean_rel`）降低了风险，但不够健壮。

**修复**：使用 `Path.is_relative_to()`

```python
def _safe_path(self, relative_path: str) -> Path:
    clean_rel = relative_path.lstrip("/\\")
    target_path = (self.base_path / clean_rel).resolve()
    if not target_path.is_relative_to(self.base_path):
        raise FileError(f"Access denied: Path {relative_path} is outside base directory.")
    return target_path
```

### H5. AI 工具暴露 delete_file / delete_dir — 提示注入可导致数据销毁

**位置**：`file.py:154-158`、`tool.py:104-125`

**问题**：`File_Handler` 通过 `getattr` 动态调用方法，仅排除 `_` 开头的方法。`delete_file` 和 `delete_dir`（含 `shutil.rmtree`）对 LLM 可见。若用户消息中嵌入提示注入，LLM 可调用 `delete_dir({"path": "."})` 删除整个项目目录。

**修复**：使用显式白名单

```python
# file.py
ALLOWED_METHODS = {"create_file", "read_file", "create_dir", "search_dir"}

def File_Handler(method: str, args: dict, pid=None, user_uuid=None) -> dict:
    ...
    if method not in ALLOWED_METHODS:
        return {"error": f"method_not_allowed: {method}"}
    func = getattr(fs, method)
    result = func(**args)
    ...
```

---

## MEDIUM

### M1. JWT 算法可被环境变量覆盖为 "none"

**位置**：`config.py:20`、`auth.py:168`

**问题**：`JWT_ALGORITHM` 可通过环境变量设为 `"none"`，PyJWT 会接受无签名 token。

**修复**：硬编码算法或白名单校验

```python
JWT_ALGORITHM = "HS256"  # 移除环境变量覆盖
```

### M2. /auth/logout 无 CSRF 防护

**位置**：`auth.py:331-336`

**问题**：恶意页面可构造表单提交到 `/auth/logout`，强制用户登出。

**修复**：添加 CSRF token 或校验 `Origin`/`Referer` 头。

### M3. /auth/refresh 依赖 Cookie 但无 CSRF 防护

**位置**：`auth.py:313-328`

**问题**：浏览器自动发送 Cookie，跨站 POST 可触发 token 刷新。`SameSite=Lax` 提供一定保护，但若被设为 `none` 则完全暴露。

**修复**：校验 `Origin` 头，或添加 CSRF token。

### M4. 无 CORS 配置

**位置**：`main.py`

**问题**：未配置 `CORSMiddleware`。前后端分离部署时请求会被浏览器拦截。

**修复**：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.com"],  # 不要用 "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### M5. 无安全响应头

**位置**：`main.py`

**问题**：缺少 `X-Content-Type-Options`、`X-Frame-Options`、`Content-Security-Policy`、`Strict-Transport-Security` 等安全头。

**修复**：添加中间件

```python
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
```

### M6. 异常信息泄露到客户端

**位置**：`file.py:166`、`loop.py:186-189`、`node.py:270-273`

**问题**：`str(e)` 直接返回给客户端，可能包含内部路径、API 密钥片段、堆栈信息。

**修复**：服务端记录完整日志，客户端返回通用错误

```python
import logging
logger = logging.getLogger(__name__)

# file.py
except Exception as e:
    logger.exception("File operation failed")
    return {"status": "error", "error": "internal_error", "message": "An internal error occurred"}

# node.py
except Exception as exc:
    logger.exception("Model call failed")
    ctx.error = "Model service temporarily unavailable"
    ctx.error_code = "MODEL_CALL_FAILED"
```

### M7. nonce 验证未覆盖所有状态变更端点

**位置**：`loop.py:212`、`data.py` 各 POST 端点

**问题**：`verify_nonce` 仅用于 `/loop/{sid}`。其他 POST 端点在 access token 有效期内（30 分钟）可被重放。

**修复**：为所有 POST 端点添加 nonce 验证，或说明为何仅聊天端点需要。

### M8. PRAGMA synchronous=OFF — 崩溃时可能丢数据

**位置**：`db.py:658`

**问题**：`synchronous=OFF` 不等待操作系统刷新写入。断电或 OS 崩溃时已提交事务可能丢失。

**修复**：改为 `synchronous=NORMAL`（WAL 模式下安全性和性能的良好平衡）

```python
conn.execute("PRAGMA synchronous=NORMAL;")
```

### M9. PyJWT 未列为显式依赖

**位置**：`pyproject.toml`

**问题**：`auth.py` 导入 `jwt`（PyJWT），但 `pyproject.toml` 未列出。作为传递依赖存在，版本变更可能导致项目中断。

**修复**：添加到 dependencies

```toml
"PyJWT>=2.8.0",
```

### M10. 锁释放未覆盖所有异常路径

**位置**：`node.py:88-95`

**问题**：`validate_node` 中 `await lock.acquire()` 获取锁，若 `release_lock_node` 自身抛异常，锁将永久持有。

**修复**：使用 `async with` 上下文管理器或 try/finally

```python
# 改造为上下文管理器模式
async def run_loop(ctx: LoopContext):
    lock = get_user_lock(ctx.user_uuid)
    async with lock:
        # 执行图引擎
        ...
```

### M11. 错误重试不区分异常类型

**位置**：`node.py:270-273`

**问题**：所有异常（含 400 Bad Request）都触发重试，最多 3 次。不应重试的错误浪费资源并延迟响应。

**修复**：区分可重试异常

```python
import httpx

RETRYABLE = (httpx.TimeoutException, httpx.ConnectError)

try:
    ...
except RETRYABLE:
    ctx.retries += 1
except Exception:
    ctx.error = str(exc)
    ctx.error_code = "MODEL_CALL_FAILED"
```

---

## LOW

### L1. 邮箱格式无校验

**位置**：`auth.py:74-75`

```python
email: str = Field(min_length=3, max_length=255)
```

**修复**：使用 `EmailStr`

```python
from pydantic import EmailStr
email: EmailStr
```

### L2. 密码最小长度仅 6 位

**位置**：`auth.py:76, 82`

**修复**：提高到 8 位，考虑复杂度要求。

### L3. logout 端点无需认证

**位置**：`auth.py:331-336`

**问题**：任何人可触发清 Cookie。虽影响有限，但应要求认证以便服务端吊销 token。

### L4. 文件内容无大小限制

**位置**：`file.py:30-36`

**问题**：`create_file` 接受任意长度 `content`，可耗尽磁盘。

**修复**：添加大小上限

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def create_file(self, path: str, content: str = "") -> str:
    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        raise FileError("File content exceeds maximum size (10MB)")
    ...
```

### L5. 分页查询无 limit 上限

**位置**：`db.py:379-392`

**问题**：`limit` 参数无上界，`limit=999999999` 可导致大查询。

**修复**：`limit = min(limit, 500)`

### L6. 生产代码使用 print()

**位置**：`db.py:739`

**修复**：换用 `logging` 模块。

### L7. Nonce 清理使用 random.random()

**位置**：`auth.py:250`

**问题**：`random` 模块非密码学安全，虽此处仅用于概率触发清理，但混用 `random` 和 `secrets` 是代码异味。

**修复**：`secrets.randbelow(100) < 5`

### L8. 依赖版本无上界

**位置**：`pyproject.toml`

**问题**：所有依赖用 `>=` 无上限，未来大版本升级可能引入破坏性变更或漏洞。

**修复**：使用兼容版本范围

```toml
"fastapi>=0.135.2,<1.0",
```

---

## 修复优先级

| 优先级 | 编号 | 问题 | 改动量 |
|--------|------|------|--------|
| P0 | C1 | JWT 空密钥 | 小 |
| P0 | H5 | AI 工具暴露删除操作 | 小 |
| P0 | H4 | _safe_path 路径检查不严谨 | 小 |
| P1 | H1 | 无限流 | 中 |
| P1 | H3 | Cookie Secure 默认 false | 小 |
| P1 | H2 | Refresh Token 无吊销 | 大 |
| P1 | M6 | 异常信息泄露 | 小 |
| P2 | M1 | JWT 算法可覆盖 | 小 |
| P2 | M4 | 无 CORS | 小 |
| P2 | M5 | 无安全头 | 小 |
| P2 | M7 | nonce 未全覆盖 | 中 |
| P2 | M8 | synchronous=OFF | 小 |
| P2 | M9 | PyJWT 未显式声明 | 小 |
| P2 | M10 | 锁释放不保证 | 中 |
| P3 | 其余 | LOW 级别问题 | 小 |
