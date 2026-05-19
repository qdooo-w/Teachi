import os

from backend.config.env import env_int


LOOP_MAX_RETRIES = env_int(os.getenv("LOOP_MAX_RETRIES"), 3)#循环最大重试次数，默认为3次
