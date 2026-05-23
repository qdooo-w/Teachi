**项目概述**

- **名称**: Teachi
- **类型**: 本地开发的 AI 聊天助手原型（后端：FastAPI + pydantic-ai；前端：Vite + Vue3）
- **目标**: 提供带鉴权、会话管理和技能（tool/skill）扩展能力的流式 AI 聊天体验，便于教学与功能验证。

**目录结构**

- backend/: 后端服务实现（FastAPI）
  - `main.py`: FastAPI 应用入口，配置中间件、生命周期与路由
  - `config.py`: 环境变量与模型/Agent 构建函数
  - `auth.py`: 注册/登录/刷新/登出（JWT + PBKDF2-HMAC）
  - `data.py`: 项目/会话/消息/文件等资源的 REST 接口
  - `loop.py`: 聊天主循环入口（`/loop/{sid}`）与 SSE 响应
  - `context.py`: `LoopContext`、`NodeName`、`LoopGraph`、节点注册器等状态机类型
  - `node.py`: 状态机各节点实现（VALIDATE/LOAD_HISTORY/BUILD_MESSAGES/CALL_MODEL/SAVE 等）
  - `db.py`: SQLite 封装（DatabaseFacade）与数据表建表逻辑
  - `file.py`: 用户/项目文件抽象与安全路径校验
  - `tool.py`: 工具注册与查询（供模型调用）
  - 其它（`logging.py`、`loop.py` 等）

- frontend/: 前端应用（Vite + Vue 3 + TypeScript）
  - `src/App.vue`: 主界面逻辑（认证、项目与会话导航、聊天 input、渲染 SSE）
  - `src/api.ts`: 前端与后端交互封装（auth、项目/会话、SSE 流处理、文件 API）
  - `src/skills.ts`: 前端技能/本地文件展示逻辑
  - components/: UI 组件集合

- future/: 设计/改进/审计文档
- pyproject.toml / frontend/package.json: 依赖与运行脚本

**整体架构概览**

- 前端（浏览器）
  - 负责认证 UI、项目/会话管理、编辑并发送消息、接收 SSE 增量并渲染。
  - 将 `access_token` 存入 `localStorage`，使用 `Authorization: Bearer` 发起受保护请求。

- 后端（FastAPI）
  - 认证层：基于 JWT 的 `access_token` + `refresh_token` 机制；`auth.py` 实现注册/登录/刷新/登出。
  - 资源层：`data.py` 提供 CRUD 与文件操作接口，所有操作在调用前使用 `get_current_user` 校验身份。
  - 聊天引擎：基于一个轻量的有向状态机（LoopGraph）驱动聊天生命周期，使用 SSE 返回模型增量输出。
  - 模型访问：通过 `pydantic_ai` 封装 Agent 与第三方模型提供者（OpenAIProvider）进行交互；技能（skills）通过 `pydantic_ai_skills` 注入能力。
  - 持久层：使用 SQLite（`DatabaseFacade`）持久化用户、项目、会话、消息、nonces（防重放）等。

**实现方式（关键点）**

- 验证与权限
  - `backend/auth.py` 使用 PBKDF2-HMAC 做密码哈希，生成 `access`（短期）和 `refresh`（长期）JWT，`backend/config.py` 提供算法与 secret 配置。
  - 前端通过 `api.ts` 提供的 `login`/`register`/`refreshAccessToken`/`logout` 封装调用。

- 状态机 + 节点（聊天引擎）
  - `LoopGraph`：声明节点（`NodeName`）间的边、入口节点与路由策略。
  - `register_node` 装饰器：在 `node.py` 中把具体逻辑函数注册到 `_registry`。
  - `run_loop`（引擎）：取当前节点函数执行，依据节点返回或图的候选边决定下一节点。异常与重试逻辑集中处理。
  - 优点：把流程拆分为小、可单测的节点；便于加入重试、stop、版本切换和工具调用的横切逻辑。

- 流式模型调用与 SSE
  - `node.call_model_node` 使用 `Agent.run_stream_events(...)` 接收 `PartDeltaEvent` / `PartEndEvent` / `AgentRunResultEvent` 等，向 `ctx.sse_queue` 推送结构化事件并由 `stream_response` 以 SSE 帧发送到前端。
  - 前端通过 `fetch` 的 `response.body.getReader()` 解析 SSE 帧（`text_delta`、`tool_call`、`tool_result`、`done`），实现增量渲染。

- 技能（skills）与工具（tools）
  - 三层技能目录：全局（`SKILL_STORAGE_DIR`）/项目/用户；加载时会给每层技能名加 `global-`/`project-`/`user-` 前缀以示作用域区分。
  - 工具注册由 `backend/tool.py` 管理，`/tools/registry` 提供可用工具名，模型只能在能力许可范围内调用。工具调用在 SSE 中只回传 `tool_name` 与 `status`（不直接暴露参数或输出），以保护隐私和实现解耦。

- 数据设计要点（SQLite）
  - 表：users, projects, sessions, messages, nonces
  - messages 包含 `msg_id`, `sid`, `kind`（user/assistant/tool_call/tool_result 等），`raw_json`（序列化的 ModelMessage），`parent_msg_id`，`version`，`is_latest`。
  - 支持：按会话列出最新消息、消息版本记录与切换、基于 parent 的版本管理、非对称删除（外键 ON DELETE CASCADE）。

**聊天请求（send）完整流程（简要）**

1. 前端发送 `POST /loop/{sid}`，body 带 `pid`, `action=send`, `message`，header 带 `Authorization` 与 `X-Nonce`。
2. 后端 `chat_loop` 通过 `get_current_user` 验证 JWT，通过 `verify_nonce` 做重放防护，构造 `LoopContext` 并返回 `StreamingResponse`（开始 SSE）。
3. 引擎 `run_loop` 按 `VALIDATE` → `LOAD_HISTORY` → `BUILD_MESSAGES` → `CALL_MODEL` → `SAVE` → `RELEASE_LOCK` 执行：加载会话历史、构建模型消息、调用 Agent 流式获取事件、把增量事件发送到 SSE 队列并最终把新消息保存到 DB。
4. 前端实时接收 `text_delta` 渲染增量文本，遇到 `done` 后刷新消息列表并显示最终消息。

**状态机（为什么使用）**

- 将聊天的复杂流程（权限、历史加载、模型调用、工具调用、保存、重试）拆成若干明确职责的节点，增强可测试性与可维护性；在并发场景下也能更方便控制锁与任务生命周期。

**开发与本地运行（快速开始）**

- 后端（Python >= 3.13）

```bash
# 安装依赖（使用 uv 工具链的示例）
uv sync
uv run --env-file .env uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

必填环境变量（示例）:

- `JWT_SECRET`=...
- `MODEL_PROVIDER_API_KEY`=...
- `MODEL_BASE_URL`=... (可选)
- `MODEL_NAME`=...
- `CORS_ALLOW_ORIGINS`=https://localhost:5173,http://localhost:5173

- 前端（Node.js）

```bash
cd frontend
npm install
npm run dev
```

前端环境变量示例（`frontend/.env`）:

```
VITE_API_BASE_URL=http://localhost:8000
VITE_DEV_API_PROXY_TARGET=http://localhost:8000
```

**部署注意事项**

- 生产务必设置强随机 `JWT_SECRET` 并使用 HTTPS（刷新令牌的 Cookie 应设置 secure）。
- `MODEL_PROVIDER_API_KEY` 不要提交到仓库，使用 Secret 管理。模型 Provider 的带宽/费用需评估。
- SQLite 适合开发或轻量部署；生产可替换为 PostgreSQL，并调整 `DatabaseFacade` 实现。
- 考虑将 Agent 的外呼、工具调用、技能加载改为可配置的授权策略与审计。

**扩展建议**

- 将 `LoopGraph` 的路由策略由“取第一候选”换成使用一个简单决策 Agent 或规则引擎，以支持更复杂的分支。
- 为 `node` 添加更细粒度的单元测试（每个节点的输入/输出）。
- 提供技能市场或 UI 让用户通过前端上传/管理技能文件，并在后端做权限隔离。
- 选项：把消息存储拆成长文本存储（对象存储）与索引（数据库），以支持大型会话和附件。

**常见问题（FAQ）**

- Q: 为什么使用 SSE？
  - A: SSE 简洁且与浏览器原生兼容，适合模型输出的单向增量流。需要双向或更复杂的信道时可以考虑 WebSocket。

- Q: 如何实现多模型或模型切换？
  - A: `backend/config.py` 提供 `GetProvider()` 工厂，可在 Agent 创建时注入不同 provider 或 model name。

- Q: 安全上需要注意什么？
  - A: 保护 `JWT_SECRET`、限制 refresh token 的传输策略（HttpOnly/secure/sameSite）、对上传的技能或文件做 sandbox/校验以防远程代码执行。

---