import os

from backend.config.env import env_bool, env_csv


APP_NAME = os.getenv("APP_NAME", "Learnova Backend")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_REQUESTS = env_bool(os.getenv("LOG_REQUESTS"), True)

CORS_ALLOW_ORIGINS = env_csv(
    os.getenv("CORS_ALLOW_ORIGINS"),
    "https://localhost:5173,http://localhost:5173",
)
#CORS配置，允许来自指定来源的跨域请求