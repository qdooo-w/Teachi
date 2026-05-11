# 后端 API 接口文档

本文档根据 `backend/` 代码审阅后整理，只描述当前后端真实暴露的接口意义、请求数据、返回体和必须携带的数据，不包含调用示例。

## 基础约定

| 项 | 说明 |
|---|---|
| 框架 | FastAPI |
| Base URL | 后端未设置统一 API 前缀 |
| Auth 路由前缀 | `/auth` |
| Chat 路由前缀 | `/loop` |
| CORS | 由 `CORS_ALLOW_ORIGINS` 环境变量控制 |
| JSON 请求 | 除 SSE 流式响应外，请求和响应均按 JSON 处理 |
| 时间字段 | `float`，Unix 时间戳，单位秒 |

## 认证与公共携带数据

除特别标明无需认证的接口外，请求必须携带：

| 位置 | 名称 | 类型 | 说明 |
|---|---|---|---|
| Header | `Authorization` | string | `Bearer <access_token>` |

`/loop/{sid}` 还必须额外携带防重放请求头：

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
| `parent_msg_id` | string \| null | regenerate 版本所属的父消息 ID |
| `version` | int | 版本号 |
| `is_latest` | int | 是否为当前启用版本，`1` 表示是，`0` 表示否 |

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
| `messages` | `MessageItem[]` | 消息列表，按 `timestamp` 升序排列；当前实现返回该会话下所有已保存消息（包含历史版本），不按 `is_latest` 过滤，前端需要自行以 `is_latest=1` 过滤 |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 404 | `{ code: "RESOURCE_NOT_FOUND", message: "Session not found" }` | 会话不存在或不属于当前用户 |

### GET `/messages/{msg_id}/versions`

意义：获取以某条消息为 `parent_msg_id` 的所有版本消息。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `msg_id` | string | 是 | 父消息 ID |

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `versions` | `MessageVersionItem[]` | 版本列表，按 `version` 升序排列；没有匹配版本时为空数组 |

`MessageVersionItem`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `msg_id` | string | 版本消息 ID |
| `kind` | string | 消息类型 |
| `raw_json` | string | Pydantic AI `ModelMessage` 序列化后的 JSON 字符串 |
| `version` | int | 版本号 |
| `is_latest` | int | 是否当前启用版本 |
| `timestamp` | float | 消息时间 |
| `created_at` | float | 记录创建时间 |

### POST `/messages/{msg_id}/switch-version`

意义：切换某个 regenerate 版本为当前启用版本。

认证：需要 `Authorization: Bearer <access_token>`。

路径参数：

| 名称 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `msg_id` | string | 是 | 路由保留参数；当前实现不使用该值，实际切换目标由请求体 `target_version_msg_id` 决定 |

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `target_version_msg_id` | string | 是 | 要切换到的版本消息 ID，必须属于当前用户且必须有 `parent_msg_id` |

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 切换成功时为 true |
| `switched_msg_id` | string | 已切换到的消息 ID |

错误：

| 状态码 | detail | 说明 |
|---|---|---|
| 400 | `{ code: "SWITCH_FAILED", message: "Failed to switch version" }` | 目标消息不存在、不属于当前用户，或不是可切换的版本消息 |
| 422 | 参数校验错误 | 请求体缺少 `target_version_msg_id` |

## 工具接口

### GET `/tools/registry`

意义：获取后端 `backend.tool` 注册表中的工具名称。

认证：无需认证。

请求体：无。

成功返回：`200 OK`

返回体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `tools` | `string[]` | 已通过 `@register_tool` 注册的工具名，按字母排序 |
| `global_allowed_tools` | `string[]` | 当前实现与 `tools` 相同 |

说明：当前 `backend.tool` 中没有任何被 `@register_tool` 装饰的具体工具函数，因此两个字段都会返回空数组。AI 模型在 `/loop/{sid}` 中调用的「技能」由 `SkillsCapability` 从三个 skills 目录加载，和该注册表不是同一个来源（参见下方「聊天循环接口」）。

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
| `message` | string | 否 | 空字符串 | 用户输入文本；`send` 时去除空白后不能为空 |
| `parent_msg_id` | string \| null | 否 | null | `regenerate` 时必填，表示要重新生成的父消息 ID |
| `allowed_tools` | `string[]` \| null | 否 | null | 前端传入的工具限制列表；当前路由接收并放入运行上下文，不在路由层校验 |

成功返回：`200 OK`

响应类型：`text/event-stream`

SSE 数据帧格式：每帧为 `data: <JSON>`，以空行分隔。

#### action 行为

| action | 意义 | 额外要求 | 主要行为 |
|---|---|---|---|
| `send` | 发送新用户消息并生成回复 | `message` 不能为空 | 加载历史、追加当前输入、调用模型、保存新产生的消息、返回流式事件 |
| `regenerate` | 基于指定父消息重新生成回复 | `parent_msg_id` 必须存在且属于当前用户 | 加载历史并在 `parent_msg_id` 前截断，重新调用模型，保存为该父消息的新版本 |
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
| `BAD_REQUEST` | 请求数据不合法 | `send` 的 `message` 为空，或 `regenerate` 缺少 `parent_msg_id` |
| `RESOURCE_NOT_FOUND` | 资源不存在 | `parent_msg_id` 不存在或不属于当前用户 |
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
| 工具限制 | `allowed_tools` 被传入运行上下文；当前代码没有调用 `build_tools` 构建注册表工具 |

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

前端 `skills.ts` 把「技能」落地为 `skills/<name>/SKILL.md` 文件，全部通过上述文件接口读写。后端在 `/loop/{sid}` 调用模型时，`SkillsCapability` 会扫描以下三个目录：

- `SKILL_STORAGE_DIR`（全局，默认 `<项目根>/data/skills`）
- 项目的 `skills` 目录（`data/{user_uuid}/{pid}/skills`）
- 用户的 `skills` 目录（`data/{user_uuid}/skills`）

因此前端的 Skill 管理只是文件 API 上的一层惯例，不需要独立的 Skill 路由。

