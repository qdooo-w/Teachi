import os

from backend.config.env import env_bool, env_float, env_int, normalize_samesite


JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable must be set and non-empty")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = env_int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"), 30)
REFRESH_TOKEN_EXPIRE_DAYS = env_int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"), 7)

REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")
REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/auth")
REFRESH_COOKIE_SECURE = env_bool(os.getenv("REFRESH_COOKIE_SECURE"), False)
REFRESH_COOKIE_SAMESITE = normalize_samesite(os.getenv("REFRESH_COOKIE_SAMESITE"), "lax")

NONCE_EXPIRY_SECONDS = env_int(os.getenv("NONCE_EXPIRY_SECONDS"), 300)
NONCE_CLEANUP_PROBABILITY = env_float(os.getenv("NONCE_CLEANUP_PROBABILITY"), 0.05)
