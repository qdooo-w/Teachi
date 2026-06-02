本项目是一个以Skill社区、Skill构建、Skill调用为核心的助教agent
前端使用Vue+Vite构建，后端使用FastAPI配置路由，使用Pydantic AI作为模型循环的核心。


使用` uv sync `进行项目依赖项的配置

使用 uvicorn 等 ASGI服务器进行后端的启用 app位于main.py中To start the backend, use an ASGI server such as uvicorn. The app is located in main.py.

本人还在学习中。

目前开发阶段的部署：

### 后端配置与部署

1. **环境配置**：
   在项目根目录下新建 `.env` 文件，输入以下配置参数：

   * **核心配置**：
     * `JWT_SECRET`：用于 JWT 签名与验证的密钥（必填，生产环境必须设定且保密，推荐使用足够长的随机字符串）。
     * `DATABASE_PATH`：SQLite 数据库路径，默认为项目根目录下的 `data/project.db`。
     * `CORS_ALLOW_ORIGINS`：跨域允许的来源列表（以逗号分隔，默认 `https://localhost:5173,http://localhost:5173`）。
     * `APP_NAME`：应用名称，默认 `Learnova Backend`。
     * `LOG_LEVEL`：日志级别（如 `INFO`, `DEBUG`, `WARNING`, `ERROR`），默认 `INFO`。
     * `LOG_REQUESTS`：是否打印 HTTP 请求日志（`true`/`false`），默认 `true`。
   * **大语言模型（LLM）配置**：
     * `MODEL_PROVIDER_API_KEY`：模型提供商的 API Key（必填）。
     * `MODEL_BASE_URL`：模型 API 基础地址（必填）。
     * `MODEL_NAME`：默认主模型名称（必填，如 `gpt-4o`、`deepseek-chat`）。
     * `SYSTEM_INSTRUCTION`：全局默认系统提示词。
   * **默认视觉模型配置**（可选，当用户在配置中勾选“支持视觉”或大模型支持视觉时，用作视觉辅助处理）：
     * `VISION_MODEL_API_KEY`：视觉辅助模型的 API Key。若不配置，自动回退到 `MODEL_PROVIDER_API_KEY`。
     * `VISION_MODEL_BASE_URL`：视觉辅助模型的 Base URL。若不配置，自动回退到 `MODEL_BASE_URL`。
     * `VISION_MODEL_NAME`：视觉辅助大语言模型名称。
     * `VISION_MODEL_WHITELIST`：支持视觉的已知模型名关键词（以逗号分隔，如 `gpt-4o,gemini,claude-3`），用于自动匹配判断模型是否支持视觉。
   * **技能与存储配置**：
     * `SKILL_STORAGE_DIR`：全局技能存放目录，默认值为项目根目录下的 `data/skills`。
   * **安全与令牌参数**（可选）：
     * `REFRESH_COOKIE_SECURE`：是否启用安全 Cookie（`true`/`false`，生产环境推荐设为 `true`）。
     * `REFRESH_COOKIE_NAME`：Cookie 中存放 refresh token 的键名，默认 `refresh_token`。
     * `REFRESH_COOKIE_PATH`：Cookie 的作用范围路径，默认 `/auth`。
     * `REFRESH_COOKIE_SAMESITE`：Cookie SameSite 属性，默认 `lax`。
     * `REFRESH_TOKEN_EXPIRE_DAYS`：Refresh Token 有效天数，默认 `7`。
     * `ACCESS_TOKEN_EXPIRE_MINUTES`：Access Token 有效分钟数，默认 `30`。

2. **依赖安装与数据库初始化**：
   ```bash
   # 安装依赖
   uv sync
   
   # 初始化 SQLite 数据库表结构
   uv run python -m backend.db
   ```

3. **启动后端服务**：
   ```bash
   # 使用 --env-file 指定环境变量文件运行 FastAPI 服务
   uv run --env-file .env uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
   ```

### 前端配置与部署

1. **环境配置**：
   在 `frontend/` 目录下新建 `.env` 文件，输入以下配置：
   ```env
   VITE_API_BASE_URL=
   VITE_DEV_API_PROXY_TARGET=http://localhost:8000
   ```
   * `VITE_API_BASE_URL`：生产环境 API 前缀，默认为空（即使用相对路径）。
   * `VITE_DEV_API_PROXY_TARGET`：开发代理目标，默认指向 `http://localhost:8000`（如果后端地址/端口不同需修改）。

2. **依赖安装与启动**：
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

本地开发前端默认是通过 Vite Proxy 进行请求转发。
后期应该会修正。