import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.auth import router as auth_router
from backend.config import APP_NAME, CORS_ALLOW_ORIGINS, DATABASE_PATH, LOG_LEVEL, LOG_REQUESTS
from backend.community import router as community_router
from backend.data import router as data_router
from backend.db import DatabaseFacade
from backend.logging import configure_logging
from backend.loop import router as loop_router
from backend.settings import router as settings_router


configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)
db = DatabaseFacade(db_path=DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
	"""应用生命周期管理器（就是资源（例如说数据库）的初始化和清理），在应用启动时设置数据库连接，并在应用关闭时进行清理（如果需要）。"""
	logger.info("Starting backend application")
	db.setup_database()
	from backend.config import SKILL_STORAGE_DIR
	from pathlib import Path
	Path(SKILL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
	yield
	logger.info("Stopping backend application")


app = FastAPI(title=APP_NAME, lifespan=lifespan)


if LOG_REQUESTS:
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "%s %s -> %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

# 配置 CORS 中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 认证路由包含 register/login/refresh/logout。
app.include_router(auth_router)

# 数据查询与基础健康路由。
app.include_router(data_router)

# 聊天主循环路由，包含会话消息发送与 regenerate。
app.include_router(loop_router)

# 社区技能广场：上传/下载/搜索/删除。
app.include_router(community_router)

# 用户模型配置：创建/更新/激活/删除。
app.include_router(settings_router)
