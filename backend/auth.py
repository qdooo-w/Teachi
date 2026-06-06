#后续可能需要处理好旧refreshtoken的吊销
import hashlib
import hmac
import secrets
import time
import random
# 认证相关逻辑，包括注册、登录、刷新 token，以及获取当前用户等功能。
from datetime import datetime, timedelta, timezone
from typing import Literal, TypedDict, cast, Optional
# 这里使用 PyJWT 来处理 JWT 生成和验证，使用 PBKDF2-HMAC 来做密码哈希，避免引入额外的依赖库。
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, status, Query, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
    NONCE_CLEANUP_PROBABILITY,
    NONCE_EXPIRY_SECONDS,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from backend.db import DatabaseFacade
from backend.db_dep import get_db
import os
import logging
from backend.registration_service import get_registration_service

logger = logging.getLogger(__name__)

# ==================== 配置 ====================
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
TEMP_TOKEN_EXPIRE_MINUTES = int(os.getenv("TEMP_TOKEN_EXPIRE_MINUTES", "5"))

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

# 令牌类型：访问令牌和刷新令牌。
TokenType = Literal["access", "refresh"]


class UserRecord(TypedDict):
    """数据库用户对象（认证层实际用到的字段）。"""

    uuid: str
    username: str
    email: str
    password_hash: str
    role: str
    self_description: Optional[str]
    major: Optional[str]
    head_file: Optional[str]
    created_at: float


class SafeUser(TypedDict):
    """User object safe for use in endpoints - excludes password_hash."""

    uuid: str
    username: str
    email: str
    role: str
    self_description: Optional[str]
    major: Optional[str]
    head_file: Optional[str]
    created_at: float

class TokenPayload(TypedDict):
    """JWT 载荷对象。"""

    sub: str    
    type: TokenType
    iat: int
    exp: int


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class SetPasswordRequest(BaseModel):
    temp_token: str
    username: Optional[str] = Field(default=None, min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class RegisterEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class LoginRequest(BaseModel):
    """登录请求模型，包含 email 和 password 字段。"""
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class RefreshRequest(BaseModel):
    """刷新访问令牌请求模型，只包含 refresh_token 字段。"""
    refresh_token: str = Field(min_length=1)


class UserOut(BaseModel):
    """用户信息输出模型，不包含敏感字段。"""
    uuid: str
    username: str
    email: str
    role: str
    self_description: Optional[str] = None
    major: Optional[str] = None
    head_file: Optional[str] = None
    created_at: float


class TokenPair(BaseModel):
    """登录/刷新时返回的 token 对。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenOut(BaseModel):
    """只返回 access token，refresh token 改由 HttpOnly Cookie 承载。"""

    access_token: str
    token_type: str = "bearer"


# 使用 PBKDF2-HMAC 做密码哈希，不引入额外依赖，便于先把链路跑通。
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return f"{salt}${digest.hex()}"


# 比较时使用常量时间比较，减少时序攻击风险。
def verify_password(password: str, stored_password_hash: str) -> bool:
    """验证密码是否匹配存储的哈希值。"""
    try:
        salt_hex, digest_hex = stored_password_hash.split("$", 1)
    except ValueError:
        return False

    current_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        120000,
    ).hex()
    return hmac.compare_digest(current_digest, digest_hex)


def _build_token(user_uuid: str, token_type: TokenType, expires_delta: timedelta) -> str:
    """生成 JWT 令牌的内部函数，统一构建 payload 和签名逻辑。"""
    now = datetime.now(timezone.utc)#获取当前 UTC 时间，确保时间相关字段的一致性和正确性。
    payload = {
        "sub": user_uuid,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user_uuid: str) -> str:
    return _build_token(
        user_uuid=user_uuid,
        token_type="access",
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_uuid: str) -> str:
    return _build_token(
        user_uuid=user_uuid,
        token_type="refresh",
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    """解码并验证 JWT 令牌，确保类型和有效性。解析JWT判断是否过期，是否有效"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch")

    user_uuid = payload.get("sub")
    if not user_uuid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # 这里做显式转换，帮助阅读和类型提示。
    typed_payload: TokenPayload = {
        "sub": str(payload["sub"]),
        "type": cast(TokenType, payload["type"]),
        "iat": int(payload["iat"]),
        "exp": int(payload["exp"]),
    }
    return typed_payload#返回解码后的JWT载荷，包含用户UUID、令牌类型、签发时间和过期时间等信息


def _ensure_user_record(user: dict | None) -> UserRecord:
    """把数据库查询结果规范成认证层使用的用户对象。"""

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return cast(UserRecord, user)


def get_current_user_uuid(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """从 Authorization 头中提取访问令牌，解码并验证后返回用户 UUID"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    token_payload = decode_token(credentials.credentials, expected_type="access")
    return token_payload["sub"]


def verify_nonce(
    x_nonce: str | None = Header(None, alias="X-Nonce"),
    x_nonce_ts: float | None = Header(None, alias="X-Nonce-Timestamp"),
    user_uuid: str = Depends(get_current_user_uuid),
    db: DatabaseFacade = Depends(get_db),
) -> None:
    """
    FastAPI 依赖项：验证 Nonce 以防重放攻击。
    """
    if not x_nonce or not x_nonce_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NONCE_MISSING",
                "message": "X-Nonce and X-Nonce-Timestamp headers are required",
            },
        )

    now = time.time()
    if abs(now - x_nonce_ts) > NONCE_EXPIRY_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NONCE_EXPIRED",
                "message": "Nonce has expired or clock skew is too large",
            },
        )

    # 尝试在数据库中记录（利用唯一约束）
    success = db.nonces.use_nonce(x_nonce, user_uuid, x_nonce_ts)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NONCE_REPLAY",
                "message": "Nonce already used (replay attack detected)",
            },
        )

    # 随机触发过期 Nonce 的清理（约 5% 的请求会触发）
    if random.random() < NONCE_CLEANUP_PROBABILITY:
        expiry_threshold = now - NONCE_EXPIRY_SECONDS * 2
        db.nonces.clean_old_nonces(expiry_threshold)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """把 refresh token 写入 HttpOnly Cookie。"""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite=REFRESH_COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """清空 refresh token Cookie。"""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
    )


@router.post("/register", status_code=status.HTTP_200_OK)
async def request_registration(
    payload: RegisterEmailRequest,
    db: DatabaseFacade = Depends(get_db)
):
    email = payload.email.strip()

    # 1. 校验邮箱域名后缀是否允许
    service = get_registration_service()
    allowed_domains_str = os.getenv("ALLOWED_EMAIL_DOMAINS", "").strip()
    if allowed_domains_str:
        allowed_domains = [d.strip() for d in allowed_domains_str.split(",") if d.strip()]
        if not any(email.endswith(f"@{domain}") for domain in allowed_domains):
            raise HTTPException(status_code=400, detail="该邮箱后缀不在允许的注册白名单中")

    # 2. 检查本地数据库是否已经存在该邮箱
    existing = db.users.get_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 3. 将邮箱写入 SeaTable 触发自动化
    try:
        success = await service.create_registration_request(email)
        if not success:
            raise HTTPException(status_code=500, detail="触发注册验证邮件失败，请稍后重试")
    except Exception as e:
        logger.error(f"发送注册请求失败: {e}")
        raise HTTPException(status_code=503, detail="服务暂时不可用，请稍后再试")

    return {"message": "验证邮件已发送，请检查邮箱完成注册"}


@router.post("/login", response_model=AccessTokenOut)
def login_user(payload: LoginRequest, response: Response, db: DatabaseFacade = Depends(get_db)) -> AccessTokenOut:
    """登录流程：验证用户凭据，生成访问令牌和刷新令牌，并通过 HttpOnly Cookie 返回刷新令牌。"""
    user = db.users.get_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user_record = cast(UserRecord, user)

    if not verify_password(payload.password, user_record["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user_record["uuid"])
    refresh_token = create_refresh_token(user_record["uuid"])
    _set_refresh_cookie(response, refresh_token)
    return AccessTokenOut(access_token=access_token)


@router.post("/refresh", response_model=AccessTokenOut)
def refresh_access_token(request: Request, response: Response, db: DatabaseFacade = Depends(get_db)) -> AccessTokenOut:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token cookie")

    token_payload = decode_token(refresh_token, expected_type="refresh")
    user_uuid = token_payload["sub"]

    user = db.users.get_by_uuid(user_uuid)
    _ensure_user_record(user)

    access_token = create_access_token(user_uuid)
    new_refresh_token = create_refresh_token(user_uuid)
    _set_refresh_cookie(response, new_refresh_token)
    return AccessTokenOut(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    """退出登录：清除 refresh token Cookie。"""
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT#因为fastapi默认的相应码返回只有在你返回了一个非空响应体才会生效，因此这里需要自己补全
    return response#返回空响应保证可读性


def get_current_user(user_uuid: str = Depends(get_current_user_uuid), db: DatabaseFacade = Depends(get_db)) -> SafeUser:
    """根据用户 UUID 获取当前用户信息，供其他接口使用"""
    user = db.users.get_by_uuid(user_uuid)
    user = _ensure_user_record(user)

    return SafeUser(
        uuid=user["uuid"],
        username=user["username"],
        email=user["email"],
        role=user["role"],
        self_description=user.get("self_description"),
        major=user.get("major"),
        head_file=user.get("head_file"),
        created_at=user["created_at"],
    )

@router.get("/me", response_model=UserOut)
def read_current_user(current_user: SafeUser = Depends(get_current_user)) -> UserOut:
    """返回当前已登录用户的基础信息（用于前端展示用户名等）。"""
    return UserOut(
        uuid=current_user["uuid"],
        username=current_user["username"],
        email=current_user["email"],
        role=current_user["role"],
        self_description=current_user.get("self_description"),
        major=current_user.get("major"),
        head_file=current_user.get("head_file"),
        created_at=float(current_user["created_at"]),
    )


# ==================== 新增端点：邮箱验证 ====================
@router.get("/verify")
async def verify_email(
    code: str = Query(...),
    db: DatabaseFacade = Depends(get_db),
):
    service = get_registration_service()
    try:
        result = await service.verify_code(code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not result:
        raise HTTPException(status_code=404, detail="Invalid verification code")

    if result["expires_at"] < datetime.now(timezone.utc):
        await service.mark_expired(result["identifier"])
        raise HTTPException(status_code=400, detail="Verification link expired")

    # 检查本地是否已存在该邮箱用户
    existing = db.users.get_by_email(result["email"])
    is_reset = "true" if existing is not None else "false"

    # 生成临时 JWT（5分钟有效）
    exp_dt = datetime.now(timezone.utc) + timedelta(minutes=TEMP_TOKEN_EXPIRE_MINUTES)
    temp_token = jwt.encode(
        {
            "email": result["email"],
            "row_id": result["identifier"],
            "is_reset": existing is not None,
            "exp": int(exp_dt.timestamp()),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    redirect_url = f"{FRONTEND_BASE_URL}/set-password?temp_token={temp_token}&is_reset={is_reset}"
    return RedirectResponse(url=redirect_url, status_code=302)


# ==================== 新增端点：设置密码 ====================
@router.post("/set-password", response_model=AccessTokenOut)
async def set_password(
    req: SetPasswordRequest,
    response: Response,
    db: DatabaseFacade = Depends(get_db),
):
    # 1. 解码临时 token
    try:
        payload = jwt.decode(req.temp_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
        identifier = payload.get("row_id")
        if not email or not identifier:
            raise HTTPException(status_code=400, detail="Invalid token payload")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Temporary token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")

    # 2. 检查邮箱是否已注册，决定是重置密码还是注册新用户
    existing_user = db.users.get_by_email(email)
    
    if existing_user:
        # 重置密码
        password_hash = hash_password(req.password)
        db.users.update_password(existing_user["uuid"], password_hash)
        user_uuid = existing_user["uuid"]
    else:
        # 新注册
        if not req.username or not req.username.strip():
            raise HTTPException(status_code=400, detail="Username is required for registration")
        password_hash = hash_password(req.password)
        try:
            new_user = db.users.create(
                username=req.username.strip(),
                email=email,
                password_hash=password_hash,
            )
            user_uuid = new_user["uuid"]
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            raise HTTPException(status_code=409, detail="User already exists")

    # 3. 更新验证码对应的注册状态为已完成
    service = get_registration_service()
    await service.mark_registered(identifier)

    # 4. 生成正式 token
    access_token = create_access_token(user_uuid)
    refresh_token = create_refresh_token(user_uuid)
    _set_refresh_cookie(response, refresh_token)

    return AccessTokenOut(access_token=access_token)


# ==================== 新增端点：请求重置密码 ====================
@router.post("/password-reset/request", status_code=status.HTTP_200_OK)
async def request_password_reset(
    payload: RegisterEmailRequest,
    db: DatabaseFacade = Depends(get_db)
):
    email = payload.email.strip()

    # 1. 校验邮箱域名后缀是否允许
    service = get_registration_service()
    allowed_domains_str = os.getenv("ALLOWED_EMAIL_DOMAINS", "").strip()
    if allowed_domains_str:
        allowed_domains = [d.strip() for d in allowed_domains_str.split(",") if d.strip()]
        if not any(email.endswith(f"@{domain}") for domain in allowed_domains):
            raise HTTPException(status_code=400, detail="该邮箱后缀不在允许的白名单中")

    # 2. 检查本地数据库是否已经存在该邮箱
    existing = db.users.get_by_email(email)
    if not existing:
        raise HTTPException(status_code=404, detail="该邮箱尚未注册")

    # 3. 将邮箱写入 SeaTable 触发自动化
    try:
        success = await service.create_registration_request(email)
        if not success:
            raise HTTPException(status_code=500, detail="触发重置密码邮件失败，请稍后重试")
    except Exception as e:
        logger.error(f"发送重置密码请求失败: {e}")
        raise HTTPException(status_code=503, detail="服务暂时不可用，请稍后再试")

    return {"message": "验证邮件已发送，请检查邮箱完成密码重置"}


# ==================== 新增端点：修改个人资料 ====================
class UpdateProfileRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    self_description: Optional[str] = Field(default=None, max_length=1000)
    major: Optional[str] = Field(default=None, max_length=100)


@router.put("/profile", response_model=UserOut)
def update_profile(
    req: UpdateProfileRequest,
    current_user: SafeUser = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    updated = db.users.update_profile(
        user_uuid=current_user["uuid"],
        username=req.username.strip(),
        self_description=req.self_description,
        major=req.major,
        head_file=current_user.get("head_file"),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        uuid=updated["uuid"],
        username=updated["username"],
        email=updated["email"],
        role=updated["role"],
        self_description=updated.get("self_description"),
        major=updated.get("major"),
        head_file=updated.get("head_file"),
        created_at=float(updated["created_at"]),
    )


# ==================== 新增端点：上传头像 ====================
@router.post("/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: SafeUser = Depends(get_current_user),
    db: DatabaseFacade = Depends(get_db),
):
    # 限制文件类型
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        raise HTTPException(status_code=400, detail="不支持的图片格式，仅支持 jpg, jpeg, png, gif, webp")

    # 确定保存目录
    user_uuid = current_user["uuid"]
    user_dir = os.path.join("data", user_uuid, "image")
    os.makedirs(user_dir, exist_ok=True)

    # 写入前先清理该目录下的旧头像文件
    for old_file in os.listdir(user_dir):
        old_path = os.path.join(user_dir, old_file)
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except Exception as e:
                logger.warning(f"无法删除旧头像文件 {old_path}: {e}")

    # 新头像文件名
    avatar_filename = f"avatar{ext}"
    avatar_path = os.path.join(user_dir, avatar_filename)

    # 写入文件
    try:
        contents = await file.read()
        with open(avatar_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logger.error(f"写入头像文件失败: {e}")
        raise HTTPException(status_code=500, detail="头像上传失败")

    # 更新数据库中的头像路径
    head_file_val = f"data/{user_uuid}/image/{avatar_filename}"
    updated = db.users.update_profile(
        user_uuid=user_uuid,
        username=current_user["username"],
        self_description=current_user.get("self_description"),
        major=current_user.get("major"),
        head_file=head_file_val,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    return UserOut(
        uuid=updated["uuid"],
        username=updated["username"],
        email=updated["email"],
        role=updated["role"],
        self_description=updated.get("self_description"),
        major=updated.get("major"),
        head_file=updated.get("head_file"),
        created_at=float(updated["created_at"]),
    )


# ==================== 新增端点：获取头像 ====================
@router.get("/avatar/{user_uuid}")
def get_avatar(
    user_uuid: str,
    db: DatabaseFacade = Depends(get_db),
):
    user = db.users.get_by_uuid(user_uuid)
    if user and user.get("head_file"):
        file_path = user["head_file"]
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)

    # 默认头像：根据用户名生成一个带首字母的 SVG 作为 Response 返回
    username = user["username"] if user else "?"
    initial = username[0].upper() if username else "?"
    
    colors = [
        ("#8A2387", "#E94057", "#F27121"),
        ("#11998e", "#38ef7d", "#38ef7d"),
        ("#3a7bd5", "#3a6073", "#3a6073"),
        ("#00c6ff", "#0072ff", "#0072ff"),
        ("#f12711", "#f5af19", "#f5af19"),
        ("#FBD3E9", "#BB377D", "#BB377D"),
    ]
    # 使用 user_uuid 的哈希值来选择渐变配色
    color_idx = 0
    if user_uuid:
        try:
            # 简单的非密码学哈希值计算，作为配色选择的索引
            color_idx = sum(ord(char) for char in user_uuid) % len(colors)
        except Exception:
            color_idx = 0

    c1, c2, c3 = colors[color_idx]

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <defs>
    <linearGradient id="grad_{user_uuid}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{c1};stop-opacity:1" />
      <stop offset="50%" style="stop-color:{c2};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{c3};stop-opacity:1" />
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="50" fill="url(#grad_{user_uuid})" />
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" font-family="sans-serif" font-size="40" font-weight="bold">{initial}</text>
</svg>"""

    return Response(content=svg_content, media_type="image/svg+xml")
