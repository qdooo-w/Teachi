# Teachi Frontend

Vue + Tailwind 最小聊天界面，用于对接当前 FastAPI 后端。

## 已确认的最小链路

- 认证：`POST /auth/login` 获取 `access_token`，refresh token 由后端 HttpOnly Cookie 管理。
- 启动：读取 JWT `sub` 作为用户 ID，查询或创建默认项目，再查询或创建默认会话。
- 历史：`GET /sessions/{sid}/messages`，只渲染 `kind=user` 和 `kind=assistant|agent_response` 的文本内容。
- 发送：`POST /loop/{sid}`，携带 `Authorization`、`X-Nonce`、`X-Nonce-Timestamp`，用 `fetch` 读取 SSE。
- 本阶段暂不做完整项目/会话管理、附件、语音、regenerate、版本切换。

