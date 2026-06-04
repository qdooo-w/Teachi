# 后端 API 接口文档

本文档根据 `backend/` 代码审阅后整理，只描述当前后端真实暴露的接口意义、请求数据、返回体和必须携带的数据，不包含调用示例。

## 近期变更

- 2026-06-04：新增「获取模型列表」API（`POST /settings/model-configs/fetch-models`），允许用户从 OpenAI 兼容提供商获取可用模型名称列表，便于在模型配置中直接选择而无需查阅文档。
- 2026-06-02：新增账号设置 API（修改用户名、修改密码），偏好设置 API（enter_mode），user_instruction 全链路贯通；修改密码后自动清除 refresh token。
- 2026-06-01：新增多模态附件系统及相关接口与 AI 工具。实现附件上传（`POST /sessions/{sid}/attachments`）、附件列表查询（`GET /sessions/{sid}/attachments`）和附件删除（`DELETE /sessions/{sid}/attachments/{attachment_id}`）。在物理存储上以 SHA-256 哈希命名文件以去重；会话内自动按文件类型生成友好文件名（如"图片1.png"）。引入 `list_attachment` 和 `view_attachment` AI 代理工具以统一处理附件、图片及 Skill 资源；完全移除了旧有的 `is_vision_assistant` 字段及数据库字段，模型配置的视觉支持通过 `supports_vision` 字段标识，并在 API 路由中完整支持该字段的读取与写入。
- 2026-05-23（第二次）：状态机新增 `BUILD_MODEL` 节点（位于 `BUILD_MESSAGES` 与 `CALL_MODEL` 之间），负责构建 PydanticAI Agent 实例并存入 `ctx.agent`；构建失败立即跳转 `STREAM_ERROR`，错误码为 `MODEL_BUILD_FAILED`。系统提示词加载改为 `load_instruction()` 函数形式，当前仍从环境变量读取，后期可改为从文件加载。
- 2026-05-23：新增用户模型配置相关 API 接口（`/settings`），允许用户自定义 API Key、Base URL、Model Name、System Instruction、Temperature 和 Max Tokens，并实现连通性测试与配置激活机制。
- 2026-05-19：后端 API 无变更（前端参数整理不影响后端接口）。

## 基础约定

| 项 | 说明 |
|---|---|
| 框架 | FastAPI |
| Base URL | 后端未设置统一 API 前缀 |
| Auth 路由前缀 | `/auth` |
| Chat 路由前缀 | `/loop` |
| Community 路由前缀 | `/community` |
| CORS | 由 `CORS_ALLOW_ORIGINS` 环境变量控制 |
| JSON 请求 | 除 SSE 流式响应外，请求和响应均按 JSON 处理 |
| 时间字段 | `float`，Unix 时间戳，单位秒 |

## 认证与公共携带数据

除特别标明无需认证的接口外，请求必须携带：

| 位置 | 名称 | 类型 | 说明 |
|---|---|---|---|
| Header | `Authorization` | string | `Bearer <access_token>` |

以下接口还必须额外携带防重放请求头：

- `POST /loop/{sid}`
- `POST /community/skills`
- `POST /community/skills/upload`
- `POST /community/skills/{skill_id}/install`

| 位置 | 名称 | 类型 | 说明 |
|---|---|---|---|
| Header | `X-Nonce` | string | 当前请求的一次性随机字符串，同一值不可重复使用 |
| Header | `X-Nonce-Timestamp` | float | Nonce 生成时的 Unix 时间戳，允许与服务端时间相差不超过 300 秒 |

刷新令牌不通过响应体返回，而是通过 HttpOnly Cookie 写入：

| Cookie 属性 | 说明 |
|---|---|
| 名称 | 默认 `refresh_token`，可由 `REFRESH_COOKIE_NAME` 覆盖 |
| Path | 默认 `/auth`，可由 `REFRESH_COOKIE_PATH` 覆盖 |
| HttpOnly | 是 |
| Secure | 由 `REFRESH_COOKIE_SECURE` 控制，默认 false |
| SameSite | 由 `REFRESH_COOKIE_SAMESITE` 控制，默认 `lax` |
| Max-Age | `REFRESH_TOKEN_EXPIRE_DAYS` 天，默认 7 天 |

## 通用错误

FastAPI 和后端当前可能返回两类错误体：

| 结构 | 说明 |
|---|---|
| `detail: string` | 认证、token、账号等简单错误 |
| `detail: { code: string, message: string }` | 业务错误或 nonce 错误 |
| `detail: array` | FastAPI/Pydantic 参数校验错误，状态码通常为 422 |

常见认证错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 401 | `Missing access token` | 需要认证但未携带 access token |
| 401 | `Token expired` | token 已过期 |
| 401 | `Invalid token` | token 无效 |
| 401 | `Token type mismatch` | token 类型与接口要求不符 |
| 401 | `Invalid token payload` | token 载荷缺少必要字段 |
| 401 | `User not found` | token 对应用户不存在 |

## 数据结构

### UserOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `uuid` | string | 用户 ID |
| `username` | string | 用户名 |
| `email` | string | 邮箱 |
| `created_at` | float | 用户创建时间 |

### AccessTokenOut

| 字段 | 类型 | 说明 |
|---|---|---|
| `access_token` | string | JWT access token |
| `token_type` | string | 固定为 `bearer` |

### ProjectItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `pid` | string | 项目 ID |
| `projectname` | string | 项目名称 |
| `timestamp` | float | 项目更新时间 |
| `created_at` | float | 项目创建时间 |

### SessionItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `sid` | string | 会话 ID |
| `sessionname` | string | 会话名称 |
| `timestamp` | float | 会话更新时间 |
| `created_at` | float | 会话创建时间 |

### MessageItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `msg_id` | string | 消息 ID |
| `kind` | string | 已保存消息类型。当前 `backend.db.MessagesFacade.save_agent_messages` 会写入 `user`、`tool_call`、`tool_result`、`assistant`、`agent_response` 五种 |
| `raw_json` | string | Pydantic AI `ModelMessage` 序列化后的 JSON 字符串 |
| `timestamp` | float | 消息时间 |
| `created_at` | float | 记录创建时间 |
| `anchor_msg_id` | string \| null | 回合（turn）锚点 msg_id。同一回合内 `user` / `tool_call` / `tool_result` / `assistant` / `agent_response` 共享此值。第一条 `user` 消息的 `anchor_msg_id` 等于自身 `msg_id`（self-reference）|
| `version` | int | `0` 表示当前活跃版本；`>0` 表示历史版本（数字越大越早）。前端默认按 (anchor_msg_id, version=0) 编排活跃链 |

### CommunitySkillSummary

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 社区技能 ID |
| `owner_uuid` | string | 发布者用户 ID |
| `name` | string | Skill 名称，来自 `SKILL.md` frontmatter |
| `description` | string | Skill 描述，来自 frontmatter |
| `license` | string \| null | 可选 license |
| `compatibility` | string \| null | 可选兼容性说明 |
| `size_bytes` | int | 归档 skill 文件夹内所有文件的总字节数 |
| `downloads` | int | 安装次数 |
| `created_at` | float | 发布时间 |
| `updated_at` | float | 更新时间 |

### CommunitySkillDetail

继承 `CommunitySkillSummary`，不额外返回 skill 文件内容。社区内容本体归档在服务端 `archived_skill/{id}/`，安装时按目录复制。

### CommunitySkillListResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `skills` | `CommunitySkillSummary[]` | 当前页技能列表 |
| `total` | int | 符合过滤条件的总数 |
| `limit` | int | 当前分页 limit |
| `offset` | int | 当前分页 offset |
| `sort` | string | `popular` 或 `newest` |

### InstallResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 已安装技能名 |
| `skill_id` | string | 社区技能 ID |
| `downloads` | int | 安装后的下载计数 |

### ModelConfigItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `config_id` | string | 配置 ID |
| `config_name` | string | 配置名称 |
| `api_key` | string | API Key (已脱敏，仅显示末 4 位或短 key 的末 2 位；空 key 则为空字符串) |
| `base_url` | string | API Base URL |
| `model_name` | string | 模型名称 |
| `user_instruction` | string | 用户自定义指令，默认空字符串 |
| `temperature` | float \| null | 温度参数，默认值为 null |
| `max_tokens` | int \| null | 最大 token 数，默认值为 null |
| `is_active` | bool | 是否激活 |
| `supports_vision` | bool | 是否支持视觉 |
| `created_at` | float | 创建时间 (Unix 时间戳) |
| `updated_at` | float | 更新时间 (Unix 时间戳) |

### ModelConfigListResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `configs` | `ModelConfigItem[]` | 当前用户的模型配置列表 |

### ActiveConfigResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `config` | `ModelConfigItem \| null` | 当前激活的配置，没有激活配置时为 null |

### TestConnectionResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 测试连接是否成功 |
| `message` | string | 详细结果消息（例如 "Connection successful" 或连接失败的具体错误信息） |
| `model` | string \| null | 连接成功的模型名称 |

### FetchModelsResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 获取是否成功 |
| `models` | `string[]` | 可用模型 ID 列表，按字母排序 |
| `message` | string | 失败时的错误信息（如 API Key 无效、提供商不支持 /models 端点等） |

### AttachmentUploadResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `attachment_id` | string | 附件 ID |
| `original_filename` | string | 自动生成的会话友好文件名（如 "图片1.png", "文档2.txt"） |
| `mime_type` | string | MIME 类型 |
| `file_size` | int | 文件大小（字节数） |
| `created_at` | float | 创建时间 (Unix 时间戳) |

### AttachmentListItem

| 字段 | 类型 | 说明 |
|---|---|---|
| `attachment_id` | string | 附件 ID |
| `anchor_msg_id` | string \| null | 绑定的消息回合 anchor ID，未绑定时为 null |
| `original_filename` | string | 会话友好文件名 |
| `mime_type` | string | MIME 类型 |
| `file_size` | int | 文件大小（字节数），默认 0 |
| `has_description` | bool | 是否已生成/缓存图片或文件的描述 |
| `created_at` | float | 创建时间 (Unix 时间戳) |

### AttachmentListResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `attachments` | `AttachmentListItem[]` | 会话中的所有附件列表 |

## 认证接口

### POST `/auth/register`

意义：注册新用户。

认证：无需认证。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `username` | string | 是 | 1-50 字符 | 用户名 |
| `email` | string | 是 | 3-255 字符 | 邮箱，必须唯一 |
| `password` | string | 是 | 6-128 字符 | 密码 |

成功返回：`201 Created`

返回体：`UserOut`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 409 | `Email already exists` | 邮箱已存在 |
| 422 | 参数校验错误 | 请求体字段不符合约束 |

### POST `/auth/login`

意义：使用邮箱和密码登录，获取 access token，并通过 Cookie 下发 refresh token。

认证：无需认证。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `email` | string | 是 | 3-255 字符 | 注册邮箱 |
| `password` | string | 是 | 6-128 字符 | 密码 |

成功返回：`200 OK`

返回体：`AccessTokenOut`

额外返回数据：

| 位置 | 名称 | 说明 |
|---|---|---|
| Header | `Set-Cookie` | 写入 refresh token Cookie |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 401 | `Invalid credentials` | 邮箱不存在或密码错误 |
| 422 | 参数校验错误 | 请求体字段不符合约束 |

### POST `/auth/refresh`

意义：使用 refresh token Cookie 换取新的 access token，并轮换 refresh token Cookie。

认证：无需 Authorization header；必须携带 refresh token Cookie。

请求体：无。

必须携带：

| 位置 | 名称 | 类型 | 说明 |
|---|---|---|---|
| Cookie | `refresh_token` | string | Cookie 名称可由 `REFRESH_COOKIE_NAME` 覆盖 |

成功返回：`200 OK`

返回体：`AccessTokenOut`

额外返回数据：

| 位置 | 名称 | 说明 |
|---|---|---|
| Header | `Set-Cookie` | 写入新的 refresh token Cookie |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 401 | `Missing refresh token cookie` | 未携带 refresh token Cookie |
| 401 | `Token expired` | refresh token 已过期 |
| 401 | `Invalid token` | refresh token 无效 |
| 401 | `Token type mismatch` | token 类型不是 refresh |
| 401 | `User not found` | token 对应用户不存在 |

### POST `/auth/logout`

意义：清除 refresh token Cookie。

认证：无需认证。

请求体：无。

成功返回：`204 No Content`

返回体：无。

额外返回数据：

| 位置 | 名称 | 说明 |
|---|---|---|
| Header | `Set-Cookie` | 删除 refresh token Cookie |

### GET `/auth/me`

意义：获取当前已登录用户的基础信息。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：无。

成功返回：`200 OK`

返回体：`UserOut`

## 通用接口

### GET `/`

意义：服务根路由，用于确认服务在线。

认证：无需认证。

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `service` | string | 应用名称，来自 `APP_NAME` |
| `status` | string | 固定为 `ok` |

### GET `/health`

意义：健康检查。

认证：无需认证。

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 固定为 `healthy` |

## 项目接口

### GET `/users/{user_id}/projects`

意义：获取当前用户的项目列表。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_id` | string | 是 | 用户 ID，必须与 access token 中的用户 ID 一致 |

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `projects` | `ProjectItem[]` | 项目列表，按 `timestamp` 降序排列 |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 403 | `{ code: "FORBIDDEN", message: "Cannot access other user's projects" }` | 访问其他用户项目列表 |

### POST `/users/{user_id}/projects`

意义：为当前用户创建项目。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_id` | string | 是 | 用户 ID，必须与 access token 中的用户 ID 一致 |

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `projectname` | string | 是 | 1-100 字符 | 项目名称 |

成功返回：`201 Created`

返回体：`ProjectItem`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 403 | `{ code: "FORBIDDEN", message: "Cannot create project for other user" }` | 为其他用户创建项目 |
| 422 | 参数校验错误 | 请求体字段不符合约束 |

### PATCH `/projects/{pid}`

意义：重命名项目。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pid` | string | 是 | 项目 ID |

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `projectname` | string | 是 | 1-100 字符 | 项目新名称 |

成功返回：`200 OK`

返回体：`ProjectItem`（`timestamp` 会被更新为改名时刻）

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目不存在或不属于当前用户 |
| 422 | 参数校验错误 | 请求体字段不符合约束 |

### DELETE `/projects/{pid}`

意义：删除项目。外键 `ON DELETE CASCADE` 会级联删除该项目下的所有会话与消息，同时通过文件系统门面保留的 `data/{user_uuid}/{pid}` 目录不会被删除（当前实现不清理文件系统）。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pid` | string | 是 | 项目 ID |

请求体：无。

成功返回：`204 No Content`，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目不存在或不属于当前用户 |

## 会话接口

### GET `/projects/{pid}/sessions`

意义：获取当前用户某个项目下的会话列表。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pid` | string | 是 | 项目 ID |

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `sessions` | `SessionItem[]` | 会话列表，按 `timestamp` 降序排列 |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目不存在或不属于当前用户 |

### POST `/projects/{pid}/sessions`

意义：在当前用户某个项目下创建会话。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pid` | string | 是 | 项目 ID |

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `sessionname` | string | 是 | 1-100 字符 | 会话名称 |

成功返回：`201 Created`

返回体：`SessionItem`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目不存在或不属于当前用户 |
| 422 | 参数校验错误 | 请求体字段不符合约束 |

### PATCH `/sessions/{sid}`

意义：重命名会话。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `sessionname` | string | 是 | 1-100 字符 | 会话新名称 |

成功返回：`200 OK`

返回体：`SessionItem`（`timestamp` 会被更新为改名时刻）

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于当前用户 |
| 422 | 参数校验错误 | 请求体字段不符合约束 |

### DELETE `/sessions/{sid}`

意义：删除会话。外键 `ON DELETE CASCADE` 会级联删除该会话下的所有消息。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |

请求体：无。

成功返回：`204 No Content`，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于当前用户 |

说明：当前实现不检查会话是否正在生成；如果该会话正在运行 `send` / `regenerate`，删除会让 `save_node` 在外键约束下写入失败，但用户锁仍会通过 `RELEASE_LOCK` 释放。前端 UI 建议在会话生成过程中隐藏 / 禁用删除入口。

## 消息接口

### GET `/sessions/{sid}/messages`

意义：获取当前用户某个会话下已经保存的消息列表。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `messages` | `MessageItem[]` | 消息列表，按 `timestamp` 升序排列；返回该会话下所有消息（包含全部 `version`），前端按 `(anchor_msg_id, version=0)` 取出活跃链；按 `anchor_msg_id` 分组可拿到各回合的全部版本 |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于当前用户 |

### GET `/messages/{msg_id}/versions`

意义：查询某个回合 anchor 下的所有版本消息（含活跃版 `version=0` 与历史版 `version>0`）。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `msg_id` | string | 是 | 回合 anchor msg_id（即原回合首条 user 消息 ID）|

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `versions` | `MessageVersionItem[]` | 该 anchor 下全部消息，按 `(version ASC, timestamp ASC)` 排列；anchor 不存在或无版本时为空数组 |

`MessageVersionItem`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `msg_id` | string | 版本消息 ID |
| `kind` | string | 消息类型 |
| `raw_json` | string | Pydantic AI `ModelMessage` 序列化后的 JSON 字符串 |
| `anchor_msg_id` | string \| null | 回合 anchor msg_id |
| `version` | int | `0` 表示活跃版本，`>0` 为历史版本 |
| `timestamp` | float | 消息时间 |
| `created_at` | float | 记录创建时间 |

### POST `/messages/{msg_id}/switch-version`

意义：把某个版本切到活跃位（`version=0`）。后端会把该版本所在组与当前 `version=0` 组**整组对调**——同一回合内 `user` / `tool_call` / `tool_result` / `assistant` 等不会错位。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `msg_id` | string | 是 | 路由保留参数；当前实现不使用该值，实际切换目标由请求体 `target_version_msg_id` 决定 |

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target_version_msg_id` | string | 是 | 要切到活跃位的版本消息 ID。后端取其 `(anchor_msg_id, version)` 后整组与 `version=0` 对调 |

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 切换成功时为 true |
| `switched_msg_id` | string | 已被切到 `version=0` 的消息 ID |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "SWITCH_FAILED", message: "Failed to switch version" }` | 目标消息不存在、不属于当前用户，或缺少 `anchor_msg_id` |
| 422 | 参数校验错误 | 请求体缺少 `target_version_msg_id` |

### DELETE `/messages/{anchor_msg_id}/turn`

意义：删除某个回合当前活跃版本（`version=0`）的整组消息。历史版本（`version>=1`）保留，可后续通过版本切换调出。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `anchor_msg_id` | string | 是 | 回合 anchor msg_id |

请求体：无。

成功返回：`204 No Content`，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Active turn not found" }` | 该 anchor 没有当前活跃版本，或不属于当前用户 |

## 附件接口

### POST `/sessions/{sid}/attachments`

意义：向当前会话上传文件附件。文件限制为 20MB。

支持的 MIME 类型包括：
- 图片：`image/jpeg`, `image/png`, `image/webp`, `image/gif`
- 文本：`text/plain`, `text/markdown`, `text/csv`, `text/html`
- 其他：`application/json`, `application/pdf`

物理文件采用 SHA-256 哈希命名并在用户和会话目录下存储。同会话内相同文件只会物理写入一次（引用去重）。会话内根据上传文件的类型自动生成“图片1.png”、“文档2.txt”等友好文件名，以防 UUID 泄露给 AI 模型。对图片类型文件进行魔术字节强校验。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |

请求体：`multipart/form-data`，包含 `file` 文件字段。

成功返回：`201 Created`

返回体：`AttachmentUploadResponse`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "FILE_TOO_LARGE", message: "File size exceeds 20MB limit" }` | 文件超过 20MB 限制 |
| 400 | `{ code: "INVALID_MIME_TYPE", message: ... }` | MIME 类型不在白名单中 |
| 400 | `{ code: "INVALID_FILE_CONTENT", message: "Magic bytes validation failed" }` | 图片类型魔术字节校验失败 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于该用户 |
| 403 | `{ code: "PERMISSION_DENIED", message: ... }` | 权限不足或用户会话空间非法 |
| 500 | `{ code: "FILE_WRITE_ERROR", message: ... }` | 文件写入失败 |

### GET `/sessions/{sid}/attachments`

意义：获取指定会话下的所有附件列表。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |

请求体：无。

成功返回：`200 OK`

返回体：`AttachmentListResponse`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于该用户 |

### DELETE `/sessions/{sid}/attachments/{attachment_id}`

意义：删除指定的会话附件。当没有任何其他 DB 记录引用该物理文件路径时，会同步物理删除磁盘上的文件。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |
| `attachment_id` | string | 是 | 附件 ID |

请求体：无。

成功返回：`204 No Content`，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于该用户 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Attachment not found" }` | 附件不存在或与会话/用户不匹配 |

## 工具接口

### GET `/tools/registry`

意义：获取后端 `backend.tool` 注册表中的工具名称。

认证：无需认证。

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `tools` | `string[]` | 已通过 `@register_tool` 注册的工具名，按字母排序；当前包含 `delete_skill`, `delete_skill_file`, `list_attachment`, `view_attachment`, `write_skill_file` |
| `global_allowed_tools` | `string[]` | 当前实现与 `tools` 相同 |

说明：这些注册表工具是 AI 可调用的工具，其中：
- `write_skill_file` / `delete_skill_file` / `delete_skill` 用于修改用户级或项目级 skill 目录。
- `list_attachment` 用于列出当前会话中所有的附件（包含文件名、MIME类型、文件大小，不含 Skill 内部资源）。
- `view_attachment` 用于按友好文件名或 `skill/` 前缀路径读取附件内容。对于图片文件返回视觉描述，普通文本（Markdown, JSON, CSV 等）直接返回文本内容，Skill 图片资源返回 BinaryContent 给主模型。

这些工具使用带范围前缀的技能名作为参数：`project-<skill_name>` 表示当前项目级技能，`user-<skill_name>` 表示用户级技能。工具内部会移除前缀并写入对应的 `skills/<skill_name>/...` 目录；`global-<skill_name>` 只读，不允许通过工具修改。

## 社区技能广场接口

### GET `/community/skills`

意义：查询社区技能列表，支持关键字过滤、分页和排序。

认证：需要 `Authorization: Bearer <access_token>`。

查询参数：

| 名称 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `keyword` | string \| null | 否 | null | 关键字，匹配 `name` 或 `description` |
| `limit` | int | 否 | 20 | 1-100 |
| `offset` | int | 否 | 0 | 起始偏移 |
| `sort` | string | 否 | `popular` | `popular` 或 `newest` |

成功返回：`200 OK`

返回体：`CommunitySkillListResponse`

### GET `/community/skills/{skill_id}`

意义：读取社区技能详情，包含技能元信息。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `skill_id` | string | 是 | 社区技能 ID |

成功返回：`200 OK`

返回体：`CommunitySkillDetail`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Community skill not found" }` | 技能不存在 |

### POST `/community/skills`

意义：将当前用户的一整个 `skills/<skill_name>/` 文件夹发布到社区。后端会复制目录到项目根目录 `archived_skill/{id}/`，数据库只保存归档路径和展示元信息。

认证：需要 `Authorization: Bearer <access_token>`，并携带 nonce 请求头。

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `skill_name` | string | 是 | 当前用户私有 `skills/<skill_name>/` 文件夹名 |

成功返回：`201 Created`

返回体：`CommunitySkillDetail`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Skill folder not found" }` | 当前用户没有该技能文件夹 |
| 422 | `{ code: "SKILL_PARSE_ERROR", message: ... }` | `SKILL.md` 缺失、frontmatter 或字段校验失败，包含 name 非法 |
| 422 | 参数校验错误 | `skill_name` 为空或请求体结构不对 |
| 400/409 | nonce 相关错误 | 见上文 nonce 规则 |

### POST `/community/skills/upload`

意义：上传一个符合 Skill 目录规范的 zip 包并发布到社区。文件上传相关路由实现放在 `backend/data.py`，归档仍写入项目根目录 `archived_skill/{id}/`，数据库只保存归档路径和展示元信息。

认证：需要 `Authorization: Bearer <access_token>`，并携带 nonce 请求头。

请求体：原始 zip 二进制 body，不使用 multipart。

请求头：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `Content-Type` | string | 建议 | `application/zip`；也接受 `application/x-zip-compressed` 与 `application/octet-stream` |
| `Content-Length` | int | 否 | 若存在且超过 40MB 会直接拒绝 |

zip 约束：

| 约束 | 说明 |
|---|---|
| 大小 | 单个 zip 包压缩后不超过 40MB；解压后的文件总大小也不超过 40MB |
| 入口 | 必须包含 `SKILL.md` |
| 结构 | 支持 `SKILL.md` 位于 zip 根目录，或 zip 根目录只有一个顶层技能文件夹且该文件夹内包含 `SKILL.md` |
| 文件类型 | 只允许 `.md .txt .json .yaml .yml` 文本文件 |
| 目录 | 只允许根目录文件、`reference(s)/` 和 `assets/` 下的一层文件；上传时 `reference/` 会被规范化成 `references/` |
| 安全 | 不允许绝对路径、`.`、`..`、空路径段、NUL 字符、重复路径、符号链接和加密 zip entry |
| 元信息 | 后端重新读取 `SKILL.md` 并解析 frontmatter，要求 `name` / `description` 等规则与普通 Skill 发布一致；发布名称只看 `frontmatter.name`，不看 zip 文件名或顶层文件夹名 |

成功返回：`201 Created`

返回体：`CommunitySkillDetail`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "ZIP_VALIDATION_ERROR", message: ... }` | zip 格式损坏、解包失败等 |
| 413 | `{ code: "ZIP_VALIDATION_ERROR", message: ... }` | zip 包或解压后总大小超过 40MB |
| 415 | `{ code: "UNSUPPORTED_FILE_TYPE", message: "Only zip uploads are supported" }` | `Content-Type` 明确不是 zip |
| 422 | `{ code: "ZIP_VALIDATION_ERROR", message: ... }` | zip 结构或文件路径不符合要求 |
| 422 | `{ code: "SKILL_PARSE_ERROR", message: ... }` | `SKILL.md` 缺失、非 UTF-8、frontmatter 或字段校验失败 |
| 400/409 | nonce 相关错误 | 见上文 nonce 规则 |

### POST `/community/skills/{skill_id}/install`

意义：把社区归档技能文件夹复制到 `skills/<name>/`。默认安装到当前用户私有技能；也可指定项目技能目录。

认证：需要 `Authorization: Bearer <access_token>`，并携带 nonce 请求头。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `skill_id` | string | 是 | 社区技能 ID |

成功返回：`200 OK`

返回体：`InstallResponse`

请求体（可选）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target` | string | 否 | `user`（默认）或 `project` |
| `pid` | string \| null | 否 | `target=project` 时必填，安装到该项目的 `skills/<name>/` |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Community skill not found" }` | 技能不存在 |
| 409 | `{ code: "LOCAL_SKILL_EXISTS", message: ... }` | 目标目录已存在同名技能目录 |
| 400 | `{ code: "INVALID_SKILL_NAME", message: ... }` | 数据库中的 name 不安全或非法 |
| 400 | `{ code: "FILE_ERROR", message: ... }` | 写入本地技能失败 |
| 422 | `{ code: "VALIDATION_ERROR", message: ... }` | `target=project` 但未提供 `pid` |
| 400/409 | nonce 相关错误 | 见上文 nonce 规则 |

### DELETE `/community/skills/{skill_id}`

意义：删除自己发布的社区技能。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `skill_id` | string | 是 | 社区技能 ID |

成功返回：`204 No Content`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 403 | `{ code: "FORBIDDEN", message: "Only the author can delete this skill" }` | 不是作者 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Community skill not found" }` | 技能不存在 |

## 聊天循环接口

### POST `/loop/{sid}`

意义：会话聊天入口，使用 Server-Sent Events 返回模型生成过程和最终结束帧。

认证：需要 `Authorization: Bearer <access_token>`，并需要 `X-Nonce` 和 `X-Nonce-Timestamp`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sid` | string | 是 | 会话 ID |

请求头：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `Authorization` | string | 是 | Bearer access token |
| `X-Nonce` | string | 是 | 一次性随机字符串 |
| `X-Nonce-Timestamp` | float | 是 | Unix 时间戳，允许 300 秒时间差 |
| `Content-Type` | string | 是 | `application/json` |

请求体：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `pid` | string | 是 | 无 | 项目 ID，必须与 `sid` 所属会话同属当前用户 |
| `action` | string | 否 | `send` | 动作类型，只支持 `send`、`regenerate`、`stop` |
| `message` | string | 否 | 空字符串 | 用户输入文本；`send` 时去除空白后不能为空；`regenerate` 时为空表示沿用 anchor 原 PROMPT，非空则用作新 PROMPT |
| `anchor_msg_id` | string \| null | 否 | null | `regenerate` 必填：要重放回合的 anchor msg_id（即原回合首条 user 消息 ID）|
| `allowed_tools` | `string[]` \| null | 否 | null | 前端传入的工具限制列表；当前路由接收并放入运行上下文，不在路由层校验 |

成功返回：`200 OK`

响应类型：`text/event-stream`

SSE 数据帧格式：每帧为 `data: <JSON>`，以空行分隔。

#### action 行为

| action | 意义 | 额外要求 | 主要行为 |
|---|---|---|---|
| `send` | 发送新用户消息并生成回复 | `message` 不能为空 | 加载历史活跃链（`version=0`）、追加当前输入、调用模型、保存新产生的消息（新回合 anchor 即首条 user 消息自身），返回流式事件 |
| `regenerate` | 基于指定回合 anchor 重新生成 | `anchor_msg_id` 必须存在且为 turn anchor（self-referencing 的 user 消息）；`message` 为空表示沿用原 PROMPT，非空则覆盖 | 加载 anchor 之前的活跃链作为上下文，调用模型；保存前把 anchor 下旧消息整组 `version+=1`，新消息以同一 anchor、`version=0` 写入 |
| `stop` | 取消当前用户正在运行的生成任务 | `pid` 和 `sid` 仍需通过归属校验 | 取消当前用户运行中的任务并释放用户锁 |

#### SSE 事件体

`text_delta`：模型文本增量。

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 固定为 `text_delta` |
| `content` | string | 本次文本片段 |

`tool_call`：工具调用开始。

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 固定为 `tool_call` |
| `tool_name` | string | 工具名 |

`tool_result`：工具调用结束。

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 固定为 `tool_result` |
| `tool_name` | string | 工具名 |
| `status` | string | `success` 或 `error` |

`done`：流结束帧。无论成功、业务错误还是模型错误，流最终都会发送该帧。

| 字段 | 类型 | 必定存在 | 说明 |
|---|---|---|---|
| `type` | string | 是 | 固定为 `done` |
| `msg_id` | string | 否 | 成功保存最终回复后返回的消息 ID |
| `anchor_msg_id` | string | 否 | 本次成功生成回合的 anchor msg_id；`send` 时即新回合首条 user 消息的 ID，`regenerate` 时即原 anchor |
| `error` | string | 否 | SSE 流内错误描述 |
| `error_code` | string | 否 | SSE 流内错误码 |

当前实现只发送 `text_delta`、`tool_call`、`tool_result`、`done`。代码注释中预留了 `tool_summary`，但当前不会发送。

#### `/loop/{sid}` 的普通 HTTP 错误

这些错误发生在 SSE 流创建前，以普通 HTTP 响应返回：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "NONCE_MISSING", message: "X-Nonce and X-Nonce-Timestamp headers are required" }` | 缺少 nonce 请求头 |
| 400 | `{ code: "NONCE_EXPIRED", message: "Nonce has expired or clock skew is too large" }` | nonce 时间戳超过允许范围 |
| 409 | `{ code: "NONCE_REPLAY", message: "Nonce already used (replay attack detected)" }` | nonce 已被使用 |
| 422 | 参数校验错误 | 请求体或请求头类型无法通过校验 |
| 500 | 非结构化错误 | `action` 不是 `send`、`regenerate`、`stop` 时当前实现会在构造 `ActionKind` 时抛出未转换异常 |

#### `/loop/{sid}` 的 SSE `done` 错误码

这些错误在流内通过 `done.error` 和 `done.error_code` 返回：

| error_code | 含义 | 触发条件 |
|---|---|---|
| `FORBIDDEN` | 无权访问项目或会话 | `pid`、`sid` 不属于当前用户，或二者不匹配 |
| `SESSION_BUSY` | 当前用户已有生成任务在运行 | 同一用户同时发起多个 `send` 或 `regenerate` |
| `BAD_REQUEST` | 请求数据不合法 | `send` 的 `message` 为空，或 `regenerate` 缺少 `anchor_msg_id` |
| `RESOURCE_NOT_FOUND` | 资源不存在 | `anchor_msg_id` 不存在或不属于当前用户 |
| `MODEL_BUILD_FAILED` | Agent 构建失败 | `BUILD_MODEL` 节点无法构建 PydanticAI Agent（如 API Key 缺失、配置非法），不重试，直接终止 |
| `MODEL_CALL_FAILED` | 模型调用失败 | 模型调用异常，最多重试 3 次后仍失败，或没有收到模型结果事件 |
| `LOOP_CONFIG_ERROR` | 状态机配置错误 | 状态机节点未注册 |
| `LOOP_EXECUTION_ERROR` | 节点执行异常 | 状态机节点抛出未捕获异常 |

#### `/loop/{sid}` 的状态与保存规则

| 项 | 当前实现 |
|---|---|
| 用户锁 | 每个用户同一时间只能有一个 `send` 或 `regenerate` 运行 |
| 任务取消 | `stop` 按用户取消当前运行任务，不按会话单独取消 |
| 历史加载 | `send` 和 `regenerate` 从数据库加载当前会话最新消息历史 |
| 消息保存 | 生成结束后保存本轮新产生的 Pydantic AI 消息，并更新会话 `timestamp` |
| 技能目录 | 模型调用时加载全局、项目、用户三个 skills 目录 |
| 工具限制 | `allowed_tools` 被传入运行上下文，并用于过滤 `build_tools` 注入的注册表工具 |
| 模型配置 | 模型调用时加载用户激活的模型配置（`is_active = 1`），包含 api_key, base_url, model_name, temperature, max_tokens；若未激活/未提供配置则回退到环境变量默认值 |
| Agent 构建 | `BUILD_MODEL` 节点在每次 `send`/`regenerate` 时构建 Agent 实例并写入 `ctx.agent`；构建失败直接终止流，不重试 |
| 系统提示词 | 通过 `load_instruction()` 函数加载，当前读取环境变量 `SYSTEM_INSTRUCTION`；用户无显式传入 `instructions` 时自动调用 |

## 文件接口

用户级与项目级文件 API 是同一组语义的两条挂载线：

| 挂载点 | 文件实际根目录 | 门面类 |
|---|---|---|
| `/users/{user_id}/files` | `<项目根>/data/{user_id}` | `backend.file.UserFile` |
| `/projects/{pid}/files` | `<项目根>/data/{user_uuid}/{pid}` | `backend.file.ProjectFile` |

两组接口的请求体、响应体、错误行为都相同；差异仅在于：

- 用户级要求 `user_id` 必须等于 access token 里的用户 ID，否则 `403 FORBIDDEN`
- 项目级通过 `ProjectFile` 构造函数校验 `pid` 归属，不匹配时后端抛 `PermissionError` 并映射为 `404 RESOURCE_NOT_FOUND`（不暴露存在性）

公共行为：

- 所有路径都通过 `FileBase._safe_path` 防止 `..` 穿越；越界时抛 `FileError` → `400 FILE_ERROR`
- 读 / 写 / 列目录的内容长度受 `WriteFileRequest.content` 限制，上限 262144 字符（`max_length=256 * 1024`，Pydantic 字符数校验，非字节数）
- 读取 / 写入前会按扩展名白名单过滤：`.md .txt .json .yaml .yml .csv .xml`；其它扩展名直接返回 `415 UNSUPPORTED_FILE_TYPE`（仅对 `GET .../content` 和 `PUT .../files` 生效，`DELETE` 不做扩展名检查）
- 当路径位于 `skills/<name>/...` 时，还会额外套用 Skill 结构约束：只允许 `SKILL.md`、根目录普通文本文件、`references/`、`assets/` 以及这两个目录下的普通文本文件；skill 场景的文本白名单收紧为 `.md .txt .json .yaml .yml`

### 数据结构

#### FileListEntry

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 条目名（相对 base 的最后一段） |
| `is_dir` | bool | 是否目录 |
| `rel_path` | string | 相对 base 的完整路径 |
| `size` | int | 目录条目固定为 0；文件为字节数 |
| `updated_at` | float | `st_mtime` |

#### FileListResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `path` | string | 请求时传入的 path（原样回写） |
| `entries` | `FileListEntry[]` | 目录条目，不做排序；路径不存在或非目录时为空数组 |

#### FileContentResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `path` | string | 请求时传入的 path（原样回写） |
| `content` | string | 文本文件内容，UTF-8 |
| `size` | int | 写入或读取完成后的字节数 |
| `updated_at` | float | `st_mtime` |

### GET `/users/{user_id}/files` / `/projects/{pid}/files`

意义：列出指定目录下的文件与子目录条目。

认证：需要 `Authorization: Bearer <access_token>`。

查询参数：

| 名称 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `path` | string | 否 | `.` | 相对 base 的目录路径，不存在或非目录时返回空 `entries` |

成功返回：`200 OK`

返回体：`FileListResponse`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "FILE_ERROR", message: ... }` | 路径越界等文件系统错误 |
| 403 | `{ code: "FORBIDDEN", message: "Cannot access other user's files" }` | 仅用户级路由，`user_id` 与 token 不匹配 |
| 403 | `{ code: "FORBIDDEN", message: "Access denied" }` | 仅用户级路由，`UserFile` 校验失败 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 仅项目级路由，`pid` 不存在或不属于当前用户 |

### GET `/users/{user_id}/files/content` / `/projects/{pid}/files/content`

意义：读取指定文本文件内容。

认证：需要 `Authorization: Bearer <access_token>`。

查询参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | 是 | 相对 base 的文件路径 |

成功返回：`200 OK`

返回体：`FileContentResponse`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "FILE_ERROR", message: ... }` | 路径越界、读失败 |
| 403 | `{ code: "FORBIDDEN", ... }` | 用户级：`user_id` 不匹配或权限校验失败 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "File not found" }` | 路径不存在或不是文件 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目级：项目不存在或不属于当前用户 |
| 415 | `{ code: "UNSUPPORTED_FILE_TYPE", message: ... }` | 扩展名不在文本白名单内 |

### PUT `/users/{user_id}/files` / `/projects/{pid}/files`

意义：写入或覆盖文本文件，父目录不存在时自动创建。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `path` | string | 是 | 扩展名需在文本白名单内 | 相对 base 的文件路径 |
| `content` | string | 是 | 最长 262144 字符（`max_length=256 * 1024`）| UTF-8 文本内容 |

成功返回：`200 OK`

返回体：`FileContentResponse`（`content` 原样回写，`size` / `updated_at` 读自写入后的 stat）

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "FILE_ERROR", message: ... }` | 路径越界、写失败 |
| 403 | `{ code: "FORBIDDEN", ... }` | 用户级：`user_id` 不匹配或权限校验失败 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目级：项目不存在或不属于当前用户 |
| 415 | `{ code: "UNSUPPORTED_FILE_TYPE", message: ... }` | 扩展名不在文本白名单内 |
| 422 | 参数校验错误 | `content` 超出 262144 字符等 |

### POST `/users/{user_id}/files/directories` / `/projects/{pid}/files/directories`

意义：创建目录。当前只用于将 Skill 的虚拟 `references/` / `assets/` 目录落盘，不做通用目录管理。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | 是 | 仅允许 `skills/<name>/references` 或 `skills/<name>/assets` |

成功返回：`204 No Content`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "FILE_ERROR", message: ... }` | 路径越界、目录名非法、或不是允许的 Skill 目录 |
| 403 | `{ code: "FORBIDDEN", ... }` | 用户级：`user_id` 不匹配或权限校验失败 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目级：项目不存在或不属于当前用户 |

### DELETE `/users/{user_id}/files` / `/projects/{pid}/files`

意义：删除指定文件或目录。目录会递归删除（`shutil.rmtree`）。

认证：需要 `Authorization: Bearer <access_token>`。

查询参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | 是 | 相对 base 的文件或目录路径 |

成功返回：`204 No Content`，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "FILE_ERROR", message: ... }` | 路径越界、删除失败 |
| 403 | `{ code: "FORBIDDEN", ... }` | 用户级：`user_id` 不匹配或权限校验失败 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Path not found" }` | 目标路径不存在 |
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Project not found" }` | 项目级：项目不存在或不属于当前用户 |

### 与前端 Skill 管理的关系

前端 `skills.ts` 把「技能」落地为 `skills/<name>/` 文件夹，入口为 `SKILL.md`，全部通过上述文件接口读写。后端在 `/loop/{sid}` 调用模型时，`SkillsCapability` 会扫描以下三个目录：

- `SKILL_STORAGE_DIR`（全局，默认 `<项目根>/data/skills`）
- 项目的 `skills` 目录（`data/{user_uuid}/{pid}/skills`）
- 用户的 `skills` 目录（`data/{user_uuid}/skills`）

因此前端的 Skill 管理只是文件 API 上的一层惯例，不需要独立的 Skill 路由。


## 用户配置接口

### GET `/settings/model-configs`

意义：列出当前用户的所有模型配置。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：无。

成功返回：`200 OK`

返回体：`ModelConfigListResponse`

### POST `/settings/model-configs`

意义：创建新的模型配置。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `config_name` | string | 是 | 1-100 字符 | 配置名称 |
| `api_key` | string | 否 | max 500 字符，默认 "" | API Key |
| `base_url` | string | 否 | max 500 字符，默认 "" | API Base URL |
| `model_name` | string | 否 | max 200 字符，默认 "" | 模型名称 |
| `user_instruction` | string | 否 | max 2000 字符，默认 "" | 用户自定义指令 |
| `temperature` | float \| null | 否 | 0.0 - 2.0，默认 null | 温度参数 |
| `max_tokens` | int \| null | 否 | 1 - 128000，默认 null | 最大 token 数 |
| `is_active` | bool | 否 | 默认 false | 是否激活 |
| `supports_vision` | bool | 否 | 默认 false | 是否支持视觉 |

成功返回：`201 Created`

返回体：`ModelConfigItem`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 422 | 参数校验错误 | 请求字段格式或值越界 |

### GET `/settings/model-configs/active`

意义：获取当前用户激活的模型配置。没有激活配置时返回 `config=None`。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：无。

成功返回：`200 OK`

返回体：`ActiveConfigResponse`

### PATCH `/settings/model-configs/{config_id}`

意义：更新指定的模型配置（仅更新请求中提供的非空字段）。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config_id` | string | 是 | 模型配置 ID |

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `config_name` | string \| null | 否 | 1-100 字符，默认 null | 配置名称 |
| `api_key` | string \| null | 否 | max 500 字符，默认 null | API Key |
| `base_url` | string \| null | 否 | max 500 字符，默认 null | API Base URL |
| `model_name` | string \| null | 否 | max 200 字符，默认 null | 模型名称 |
| `user_instruction` | string \| null | 否 | max 2000 字符，默认 null | 用户自定义指令 |
| `temperature` | float \| null | 否 | 0.0 - 2.0，默认 null | 温度参数 |
| `max_tokens` | int \| null | 否 | 1 - 128000，默认 null | 最大 token 数 |
| `supports_vision` | bool \| null | 否 | 默认 null | 是否支持视觉 |

成功返回：`200 OK`

返回体：`ModelConfigItem`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Model config not found" }` | 模型配置不存在或不属于当前用户 |
| 422 | 参数校验错误 | 请求字段格式或值越界 |

### POST `/settings/model-configs/{config_id}/activate`

意义：激活指定的模型配置（同时取消当前用户其他配置的激活状态）。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config_id` | string | 是 | 模型配置 ID |

请求体：无。

成功返回：`200 OK`

返回体：`ModelConfigItem`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Model config not found" }` | 模型配置不存在或不属于当前用户 |

### POST `/settings/model-configs/deactivate`

意义：取消所有模型配置的激活状态，回到全局默认配置。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：无。

成功返回：`204 No Content`，无返回体。

### DELETE `/settings/model-configs/{config_id}`

意义：删除指定的模型配置。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config_id` | string | 是 | 模型配置 ID |

请求体：无。

成功返回：`204 No Content`，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Model config not found" }` | 模型配置不存在或不属于当前用户 |

### POST `/settings/model-configs/test-connection`

意义：用传入的原始参数测试 API 连通性（保存前预检）。传入参数优先，未提供字段回退到环境变量默认值。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `api_key` | string | 否 | max 500 字符，默认 "" | API Key |
| `base_url` | string | 否 | max 500 字符，默认 "" | API Base URL |
| `model_name` | string | 否 | max 200 字符，默认 "" | 模型名称 |
| `supports_vision` | bool | 否 | 默认 false | 是否支持视觉 |

成功返回：`200 OK`

返回体：`TestConnectionResponse`

### POST `/settings/model-configs/{config_id}/test-connection`

意义：用已保存的配置测试 API 连通性。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config_id` | string | 是 | 模型配置 ID |

请求体：无。

成功返回：`200 OK`

返回体：`TestConnectionResponse`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Model config not found" }` | 模型配置不存在或不属于当前用户 |

### POST `/settings/model-configs/fetch-models`

意义：从提供商获取可用模型列表。调用 OpenAI 兼容的 /models 端点，返回模型 ID 列表。部分提供商可能不支持该端点，此时返回 `success=false` 和相应提示。

认证：需要 `Authorization: Bearer <access_token>`。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `api_key` | string | 否 | max 500 字符，默认 "" | API Key |
| `base_url` | string | 否 | max 500 字符，默认 "" | API Base URL（需通过 SSRF 校验） |

成功返回：`200 OK`

返回体：`FetchModelsResponse`

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 422 | 参数校验错误 | base_url 格式不合法或指向内部网络 |


---

## 账号设置（/settings/account）

### GET /settings/account

意义：获取当前用户账号信息。

认证：需要 Authorization: Bearer <access_token>。

请求体：无。

成功返回：200 OK

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| uuid | string | 用户 ID |
| username | string | 用户名 |
| email | string | 邮箱 |
| created_at | float | 创建时间 |

### PATCH /settings/account/username

意义：修改当前用户的用户名。

认证：需要 Authorization: Bearer <access_token>。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| username | string | 是 | 1-50 字符 | 新用户名 |

成功返回：200 OK，返回体同 AccountInfo。

### POST /settings/account/change-password

意义：修改当前用户密码。需验证旧密码，成功后清除 refresh token Cookie，强制重新登录。

认证：需要 Authorization: Bearer <access_token>。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| current_password | string | 是 | 6-128 字符 | 当前密码 |
| new_password | string | 是 | 6-128 字符 | 新密码 |

成功返回：204 No Content，无返回体。

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | { code: "INVALID_PASSWORD", message: "当前密码不正确" } | 旧密码验证失败 |

---

## 偏好设置（/settings/preferences）

### GET /settings/preferences

意义：获取当前用户偏好设置。未设置过则返回默认值。

认证：需要 Authorization: Bearer <access_token>。

请求体：无。

成功返回：200 OK

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| enter_mode | string | 发送键模式：enter 或 ctrl_enter，默认 enter |
| updated_at | float \| null | 最后更新时间，未设置过为 null |

### PATCH /settings/preferences

意义：更新当前用户偏好设置。仅更新请求中提供的字段。

认证：需要 Authorization: Bearer <access_token>。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| enter_mode | string \| null | 否 | 仅允许 enter 或 ctrl_enter | 发送键模式 |

成功返回：200 OK，返回体同 Preferences。
