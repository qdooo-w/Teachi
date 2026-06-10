# Learnova 后端架构全景

## 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| AI 框架 | Pydantic AI (OpenAI 兼容) |
| 数据库 | SQLite (原生 `sqlite3`，无 ORM) |
| 认证 | JWT 双 token + PBKDF2 密码哈希 |
| 包管理 | uv |
| Python | 3.14 |

---

## 代码风格

- **语言**：注释大量使用中文，公共 API 用英文 docstring
- **类型标注**：Python 3.10+ 语法（`str | None`、`list[str]`）
- **模块结构**：扁平式，无深层包嵌套，所有后端代码在 `backend/` 下一层
- **Schema 定义**：Pydantic BaseModel，内联在各路由模块中，无独立 schemas 文件
- **SQL**：手写参数化查询，无 ORM

---

## 核心组件

### 1. 路由层（5 个 Router）

| Router | 文件 | 职责 |
|---|---|---|
| Auth | `auth.py` | 注册、登录、刷新 token、登出 |
| Data | `data.py` (~1315 行) | 项目/会话/消息 CRUD、会话附件管理、文件管理、ZIP 上传 |
| Loop | `loop.py` | AI 聊天循环入口，SSE 流式响应 |
| Community | `community.py` | 社区技能市场（列表/发布/安装/删除） |
| Settings | `settings.py` | 设置中心（模型配置 CRUD、测试连接、账户设置、用户偏好设置） |

### 2. 数据库门面（`db.py` ~1568 行）

`DatabaseFacade` 持有 10 个子门面，共享连接工厂：

```
db.users        → UsersFacade
db.projects     → ProjectsFacade
db.sessions     → SessionsFacade
db.messages     → MessagesFacade（含版本管理）
db.access       → AccessFacade（跨域所有权校验）
db.nonces       → NoncesFacade（防重放）
db.model_configs → ModelConfigsFacade
db.community    → CommunitySkillsFacade
db.attachments  → AttachmentsFacade
db.preferences  → UserPreferencesFacade
```

**9 张表**：`users`、`projects`、`sessions`、`messages`、`nonces`、`community_skills`、`user_model_configs`、`attachments`、`user_preferences`

**连接配置**：外键开启、WAL 模式、synchronous OFF、`sqlite3.Row` 行工厂

### 3. AI 聊天状态机（`loop.py` + `node.py` + `context.py`）

整个后端最核心的架构设计——**有向图状态机**：

```
VALIDATE → LOAD_HISTORY → BUILD_MESSAGES → BUILD_MODEL → CALL_MODEL → SAVE → STREAM_COMPLETE
                                          ↑               ↓
                                          └── RETRY (最多3次) ──┘
                                                    ↓
                                              STREAM_ERROR → RELEASE_LOCK
```

- **`LoopGraph`**（`context.py`）：声明节点和带条件的边
- **`LoopContext`**：请求级可变上下文，在节点间流转
- **`run_loop`**（`loop.py`）：引擎——执行节点、查询图获取下一步、循环
- **SSE 流式**：节点通过 `asyncio.Queue` 推送事件，生成器消费
- **并发控制**：per-user `asyncio.Lock`，防止同一用户并发生成

**节点职责**：

| 节点 | 功能 |
|---|---|
| `validate_node` | 所有权校验、获取锁、输入验证 |
| `load_history_node` | 从 DB 加载活跃消息，反序列化 ModelMessage |
| `build_messages_node` | 组装最终消息列表 |
| `build_model_node` | 构建 PydanticAI Agent（含工具、技能、用户模型配置） |
| `call_model_node` | 流式调用模型，推送 text_delta / tool_call SSE 事件 |
| `save_node` | 持久化消息，处理 regenerate 的版本递增，绑定未绑定的会话附件到回合 anchor |
| `release_lock_node` | 始终最后执行，释放锁 |

### 4. 文件系统门面（`file.py`）

- `FileBase`：安全文件操作，`_safe_path()` 防目录穿越
- `UserFile`：作用域 `data/{user_uuid}/`
- `ProjectFile`：作用域 `data/{user_uuid}/{pid}/`

### 5. AI 工具注册（`tool.py`）

`@register_tool` 装饰器注册工具 → `build_tools()` 构建工具列表注入 Agent。工具错误通过 `_with_skill_fs()` 捕获，返回结构化错误 dict，不会崩溃模型循环。

### 6. 配置中心（`config/` 包）

7 个子模块，环境变量驱动，`importlib.reload()` 支持开发时热重载：

| 子模块 | 职责 |
|---|---|
| `app.py` | APP_NAME、LOG_LEVEL、CORS |
| `auth.py` | JWT 密钥、token 有效期、cookie 设置 |
| `model.py` | 模型 Provider/Agent 工厂、prompt 文件加载、模型列表获取 |
| `paths.py` | BASE_DIR、DB 路径、技能存储目录 |
| `loop.py` | LOOP_MAX_RETRIES |
| `skill.py` | 技能命名规则、文件扩展名白名单、ZIP 限制 |
| `community.py` | 分页、排序默认值 |

---

## API 路由总览

### Auth（`/auth`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册 |
| POST | `/auth/login` | 登录（返回 access token + HttpOnly refresh cookie） |
| POST | `/auth/refresh` | 刷新 access token |
| POST | `/auth/logout` | 登出（清除 refresh cookie） |
| GET | `/auth/me` | 获取当前用户信息 |

### Data（无前缀）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 根路径健康检查 |
| GET | `/health` | 健康探测 |
| GET | `/users/{user_id}/projects` | 列出用户项目 |
| POST | `/users/{user_id}/projects` | 创建项目 |
| PATCH | `/projects/{pid}` | 重命名项目 |
| DELETE | `/projects/{pid}` | 删除项目（级联） |
| GET | `/projects/{pid}/sessions` | 列出项目会话 |
| POST | `/projects/{pid}/sessions` | 创建会话 |
| PATCH | `/sessions/{sid}` | 重命名会话 |
| DELETE | `/sessions/{sid}` | 删除会话（级联） |
| GET | `/sessions/{sid}/messages` | 列出会话消息 |
| GET | `/tools/registry` | 列出已注册 AI 工具 |
| GET | `/messages/{msg_id}/versions` | 获取消息所有版本 |
| POST | `/messages/{msg_id}/switch-version` | 切换版本组 |
| DELETE | `/messages/{anchor_msg_id}/turn` | 删除活跃轮次 |
| GET | `/users/{user_id}/files` | 列出用户文件 |
| GET | `/users/{user_id}/files/content` | 读取用户文件 |
| PUT | `/users/{user_id}/files` | 写入用户文件 |
| POST | `/users/{user_id}/files/directories` | 创建用户目录 |
| DELETE | `/users/{user_id}/files` | 删除用户文件/目录 |
| GET | `/projects/{pid}/files` | 列出项目文件 |
| GET | `/projects/{pid}/files/content` | 读取项目文件 |
| PUT | `/projects/{pid}/files` | 写入项目文件 |
| POST | `/projects/{pid}/files/directories` | 创建项目目录 |
| DELETE | `/projects/{pid}/files` | 删除项目文件/目录 |
| POST | `/sessions/{sid}/attachments` | 上传会话文件附件 |
| GET | `/sessions/{sid}/attachments` | 获取会话的所有附件 |
| DELETE | `/sessions/{sid}/attachments/{attachment_id}` | 删除会话文件附件 |
| POST | `/community/skills/upload` | ZIP 上传技能到社区 |

### Loop（`/loop`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/loop/{sid}` | 聊天循环入口（send/regenerate/stop），返回 SSE 流 |

### Community（`/community`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/community/skills` | 列出社区技能（搜索、分页、排序） |
| GET | `/community/skills/{skill_id}` | 技能详情 |
| POST | `/community/skills` | 发布技能（从本地用户技能目录） |
| POST | `/community/skills/{skill_id}/install` | 安装社区技能 |
| DELETE | `/community/skills/{skill_id}` | 删除社区技能（仅作者） |

### Settings（`/settings`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/settings/model-configs` | 列出用户模型配置 |
| POST | `/settings/model-configs` | 创建模型配置 |
| GET | `/settings/model-configs/active` | 获取当前主模型与全部启用配置 |
| PATCH | `/settings/model-configs/{config_id}` | 更新配置 |
| POST | `/settings/model-configs/{config_id}/activate` | 切换配置启用状态 |
| POST | `/settings/model-configs/deactivate` | 停用所有配置 |
| DELETE | `/settings/model-configs/{config_id}` | 删除配置 |
| POST | `/settings/model-configs/test-connection` | 用原始参数测试连接 |
| POST | `/settings/model-configs/fetch-models` | 从提供商获取可用模型列表 |
| POST | `/settings/model-configs/{config_id}/test-connection` | 用已保存配置测试连接 |
| GET | `/settings/account` | 获取当前账号信息 |
| PATCH | `/settings/account/username` | 修改用户名 |
| POST | `/settings/account/change-password` | 修改密码 |
| GET | `/settings/preferences` | 获取当前用户偏好设置 |
| PATCH | `/settings/preferences` | 更新当前用户偏好设置 |

---

## 关键节点

### 认证流程

- **双 token**：Access（30min，响应体）+ Refresh（7天，HttpOnly cookie）
- **防重放**：敏感操作需 `X-Nonce` + `X-Nonce-Timestamp` 头，DB 唯一约束，5% 概率清理过期 nonce
- **密码**：PBKDF2-HMAC-SHA256，120k 迭代，16 字节随机盐

### 消息版本管理

- `anchor_msg_id` + `version` 模型（从旧 `parent_msg_id + is_latest` 迁移而来）
- 支持同一轮对话的多版本切换（regenerate 场景）

### 技能系统

- 三作用域：global（只读）、project、user
- `SKILL.md` frontmatter（YAML）+ `references/`、`assets/` 子目录
- 社区市场支持 ZIP 上传/发布/安装，含完整安全校验（符号链接拒绝、路径穿越检查、大小限制 5MB）

### 错误处理

- HTTP 错误统一 `{"code": "...", "message": "..."}` 结构
- 状态机节点设 `ctx.error` 而非抛异常，引擎捕获未处理异常路由到 `STREAM_ERROR`
- DB 操作：`db_cursor()` 上下文管理器，异常 rollback，成功 commit
- 文件操作：所有异常包装为 `FileError`

### 附件与多模态视觉处理

- **物理存储与去重**：支持并发上传图片、文本、PDF 等类型附件，在物理存储上以 SHA-256 哈希命名文件以去重，维护文件的引用计数以进行安全删除。
- **多模态与工具链配合**：AI 代理会在会话开始或需要时通过 `view_attachment` 读取文件具体内容。
- **图片叙述生成**：若用户当前主模型不支持视觉，系统会利用启用中的视觉模型配置或环境变量 `VISION_MODEL_` 相关默认配置生成图片描述，缓存到 DB 中作为文字背景供主模型使用。

### 设置中心

- **模型配置**：用户可创建多个模型配置（API Key、Base URL、Model Name、`user_instruction` 自定义指令、Temperature、Max Tokens、`supports_vision` 视觉支持标记）。运行时最多启用两个模型；当启用两个模型时，至少一个必须是视觉理解模型。主对话优先使用非视觉启用配置，视觉启用配置作为图片理解辅助；若只启用一个视觉模型，则它同时作为主模型和视觉模型。`user_instruction` 在构建 Agent 时作为系统指令注入；`supports_vision` 标记决定测试连接时走视觉还是文本路径，也参与辅助视觉模型选择。支持通过 `fetch-models` 端点从提供商获取可用模型列表，用户可直接选择而无需手动输入模型名称。
- **账号设置**：支持修改用户名和密码。修改密码后自动清除 refresh token，强制重新登录。
- **偏好设置**：当前支持 `enter_mode`（发送键模式：`enter` 或 `ctrl_enter`），存储在 `user_preferences` 表中，首次访问返回默认值。

---

## 当前薄弱点

1. **测试覆盖极低**：仅 `test_community_zip_upload.py` 一个文件（6 个测试），无 auth/CRUD/状态机/工具测试
2. **无正式迁移框架**：`CREATE TABLE IF NOT EXISTS` + 手动 `ALTER TABLE`，靠 `scripts/` 下的独立脚本
3. **`data.py` 过大**（~1315 行）：混合了项目/会话/消息/文件/ZIP 上传多种职责
4. **无 Service 层**：业务逻辑直接写在路由处理器中，授权检查内联
