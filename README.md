本项目是一个使用Pydantic AI python库简单构建的一个具有鉴权数据调取的AI聊天库。

使用` uv sync `进行项目依赖项的配置

使用 uvicorn 等 ASGI服务器进行后端的启用 app位于main.py中To start the backend, use an ASGI server such as uvicorn. The app is located in main.py.

本人还在学习中。

目前开发阶段的部署：

- 后端
```
先自建了.env文件。需要输入的环境变量有：
JWT_SECRET,
MODEL_PROVIDER_API_KEY
MODEL_BASE_URL，
MODEL_NAME
CORS_ALLOW_ORIGINS(如果前端端口不一样，默认给localhost:5173)


uv sync之后 uv run --env-file .env uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000


```
- 前端

先自建了.env文件。需要输入的环境变量有：
```
VITE_API_BASE_URL=
VITE_DEV_API_PROXY_TARGET=http://localhost:8000(默认值，如果后端地址不同需要修改)

cd frontend
npm install
npm run dev

```
本地开发前端默认是通过Vite Proxy
后期应该会修正