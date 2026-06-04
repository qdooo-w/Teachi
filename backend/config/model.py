from __future__ import annotations

import asyncio
import os

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
import ipaddress
import logging

from openai import AuthenticationError, NotFoundError, APIConnectionError

from backend.context import ChatDeps

def load_instruction() -> str:
    """加载系统提示词。当前从环境变量读取，后期可改为从文件加载。"""
    return os.getenv("SYSTEM_INSTRUCTION", "")


def load_prompt(*filenames: str) -> Callable[[], str]:
    """返回一个从 backend/config/prompts/ 下按顺序读取并拼接多个提示词文件的函数。"""
    def _loader() -> str:
        contents = []
        for filename in filenames:
            path = Path(__file__).parent / "prompts" / filename
            contents.append(path.read_text(encoding="utf-8"))
        return "\n\n".join(contents)
    return _loader


# 保留常量以兼容现有引用
INSTRUCTION = load_instruction()
INSTUCTION = INSTRUCTION  # compat alias, will be removed in a future release

MODEL_PROVIDER_API_KEY = os.getenv("MODEL_PROVIDER_API_KEY", "")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")

# 测试连接默认超时时间（秒）
TEST_CONNECTION_TIMEOUT = 15

# 获取模型列表默认超时时间（秒）
FETCH_MODELS_TIMEOUT = 10


_logger = logging.getLogger(__name__)


def validate_base_url(url: str) -> str:
    """Validate base_url to prevent SSRF: must be http(s), must not point to private/internal networks."""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"base_url scheme must be http or https, got {parsed.scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("base_url must contain a valid hostname")
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("base_url must not point to localhost")
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("base_url must not point to a private/internal IP address")
    except ValueError:
        # Not an IP literal - it's a domain name, allow DNS resolution
        pass
    return url



# ── 视觉模型配置 ──

VISION_MODEL_API_KEY = os.getenv("VISION_MODEL_API_KEY", "")
VISION_MODEL_BASE_URL = os.getenv("VISION_MODEL_BASE_URL", "")
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "")

# 逗号分隔的已知多模态模型名关键词（大小写不敏感的子串匹配）
# 示例：VISION_MODEL_WHITELIST=gpt-4o,gemini,claude-3
_VISION_WHITELIST_RAW = os.getenv("VISION_MODEL_WHITELIST", "")
VISION_MODEL_WHITELIST: list[str] = [
    kw.strip().lower()
    for kw in _VISION_WHITELIST_RAW.split(",")
    if kw.strip()
]


def model_name_is_vision(model_name: str) -> bool:
    """判断模型名是否命中视觉白名单（大小写不敏感子串匹配）。"""
    lower = model_name.lower()
    return any(kw in lower for kw in VISION_MODEL_WHITELIST)


def active_model_supports_vision(db, user_uuid: str) -> bool:
    """判断当前用户激活的模型配置是否支持视觉。

    优先级：
    1. 激活配置的 model_name 命中白名单
    2. 激活配置的 supports_vision 字段为 True
    3. 否则返回 False
    """
    config = db.model_configs.get_active_for_user(user_uuid)
    if config is None:
        return bool(VISION_MODEL_NAME) and model_name_is_vision(VISION_MODEL_NAME)
    model_name = config.get("model_name", "")
    if model_name and model_name_is_vision(model_name):
        return True
    return bool(config.get("supports_vision"))


def get_vision_assistant_provider(db, user_uuid: str) -> "OpenAIChatModel":
    """选取视觉辅助模型，按优先级：
    1. 用户配置中 supports_vision=True 的任意一条（取第一条）
    2. 系统 env 默认视觉模型（VISION_MODEL_*）
    3. 抛出 RuntimeError
    """
    configs = db.model_configs.list_by_user(user_uuid)

    for c in configs:
        if c.get("supports_vision") or model_name_is_vision(c.get("model_name", "")):
            return GetProvider(
                api_key=c.get("api_key") or None,
                base_url=c.get("base_url") or None,
                model_name=c.get("model_name") or None,
            )
    if VISION_MODEL_NAME:
        return GetProvider(
            api_key=VISION_MODEL_API_KEY or None,
            base_url=VISION_MODEL_BASE_URL or None,
            model_name=VISION_MODEL_NAME,
        )

    raise RuntimeError(
        "没有可用的视觉辅助模型。请在用户设置中配置支持视觉的模型，"
        "或在环境变量中设置 VISION_MODEL_NAME。"
    )


def GetProvider(
    api_key: str | None = None,
    base_url: str | None = None,
    model_name: str | None = None,
) -> OpenAIChatModel:
    """构建聊天模型实例。

    优先使用传入参数，未提供时回退到环境变量默认值。
    """
    _api_key = api_key or MODEL_PROVIDER_API_KEY
    _base_url = base_url or MODEL_BASE_URL
    _model_name = model_name or MODEL_NAME

    validate_base_url(_base_url)

    if not _api_key:
        raise RuntimeError(
            "Missing API key. Please set MODEL_PROVIDER_API_KEY in environment variables "
            "or configure it in user model settings."
        )

    provider = OpenAIProvider(
        base_url=_base_url,
        api_key=_api_key,
    )
    return OpenAIChatModel(
        _model_name,
        provider=provider,
    )


def GetAgent(
    instructions: str | None = None,
    tools: list | None = None,
    capabilities: list | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model_name: str | None = None,
    model_settings: ModelSettings | None = None,
) -> Agent[ChatDeps, str]:
    """创建一个可复用的 Pydantic AI Agent。每次调用都创建新实例，注入工具 and 能力。

    优先使用传入的模型配置参数（api_key, base_url, model_name），
    未提供时回退到环境变量默认值。

    model_settings 用于传递 temperature、max_tokens 等运行时参数。
    """
    return Agent(
        GetProvider(api_key=api_key, base_url=base_url, model_name=model_name),
        instructions=instructions if instructions is not None else load_instruction(),
        tools=tools or [],
        capabilities=capabilities or [],
        deps_type=ChatDeps,
        model_settings=model_settings,
    )


async def test_connection(
    api_key: str | None = None,
    base_url: str | None = None,
    model_name: str | None = None,
    supports_vision: bool = False,
) -> dict:
    """测试模型 API 连通性。

    对于普通模型，发送一个极简文本请求验证有效性。
    对于支持视觉的模型，发送一个测试图片以专门验证其视觉接收与解析能力。
    如果视觉测试失败，会尝试回退到纯文本测试，以区分是 API 连接错误还是模型本身不支持视觉。
    返回 {"success": bool, "message": str, "model": str | None}。
    """
    try:
        model = GetProvider(api_key=api_key, base_url=base_url, model_name=model_name)
        # 使用 openai 异步客户端发送极简请求，避免 pydantic-ai Agent 的复杂依赖
        # 注意：max_tokens 不能设太小，部分模型（如思考模型）有最低 token 限制
        client = model.client  # AsyncOpenAI 客户端
    except Exception as e:
        return {
            "success": False,
            "message": f"连接初始化失败：{e}",
            "model": None,
        }

    # 1. 尝试主测试（如果 supports_vision 为 True 则测试视觉，否则测试文本）
    primary_success = False
    primary_error = None

    # 构造视觉消息
    vision_messages = []
    if supports_vision:
        from backend.config import BASE_DIR
        import base64
        image_path = BASE_DIR / "image.png"
        if image_path.is_file():
            image_bytes = image_path.read_bytes()
        else:
            # 备用单像素透明 PNG，防止文件缺失导致报错
            image_bytes = base64.b64decode(
                b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        vision_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hi, please describe this image briefly in one sentence to test our API connection."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

    # 尝试进行主测试
    try:
        messages = vision_messages if supports_vision else [{"role": "user", "content": "Hi"}]
        await asyncio.wait_for(
            client.chat.completions.create(
                model=model.model_name,
                messages=messages,
                max_tokens=64,
            ),
            timeout=TEST_CONNECTION_TIMEOUT,
        )
        primary_success = True
    except Exception as e:
        primary_error = e

    if primary_success:
        return {
            "success": True,
            "message": "Connection successful" if not supports_vision else "Vision connection successful",
            "model": model.model_name,
        }

    # 2. 如果主测试失败，且当前勾选了 supports_vision，我们需要回退测试纯文本，来排查原因
    if supports_vision:
        try:
            # 回退进行纯文本测试
            await asyncio.wait_for(
                client.chat.completions.create(
                    model=model.model_name,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=64,
                ),
                timeout=TEST_CONNECTION_TIMEOUT,
            )
            # 纯文本测试通了，说明接口地址和 API Key 是对的，但是不支持视觉
            return {
                "success": False,
                "message": f"视觉能力测试失败（API 连通正常，但该模型可能不支持视觉输入，请更换多模态/支持视觉的模型）。错误详情：{primary_error}",
                "model": model.model_name,
            }
        except Exception as text_err:
            # 纯文本也失败了，说明是 API 连通性本身的问题（例如 API Key 错误、地址无效、网络不通）
            return {
                "success": False,
                "message": f"连接失败（API 地址或 API Key 配置有误，网络超时等，且纯文本测试也未通过）。错误详情：{text_err}",
                "model": model.model_name,
            }

    # 普通文本测试失败
    return {
        "success": False,
        "message": f"连接失败（可能是 API 地址或 API Key 有误，网络超时等）。错误详情：{primary_error}",
        "model": model.model_name,
    }

async def fetch_available_models(
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """从提供商获取可用模型列表。

    调用 OpenAI 兼容的 /models 端点，返回模型 ID 列表。
    返回 {"success": bool, "models": list[str], "message": str}。
    """
    try:
        model = GetProvider(api_key=api_key, base_url=base_url, model_name="placeholder")
        client = model.client
    except ValueError as e:
        return {"success": False, "models": [], "message": f"参数校验失败：{e}"}
    except RuntimeError as e:
        return {"success": False, "models": [], "message": str(e)}

    try:
        response = await asyncio.wait_for(
            client.models.list(),
            timeout=FETCH_MODELS_TIMEOUT,
        )
        model_ids = sorted(m.id for m in response.data)
        return {"success": True, "models": model_ids, "message": ""}
    except AuthenticationError:
        return {"success": False, "models": [], "message": "API Key 无效或无权限访问模型列表"}
    except NotFoundError:
        return {"success": False, "models": [], "message": "该提供商不支持模型列表查询（/models 端点不可用）"}
    except APIConnectionError as e:
        return {"success": False, "models": [], "message": f"网络连接失败：{e}"}
    except asyncio.TimeoutError:
        return {"success": False, "models": [], "message": "获取模型列表超时，请检查网络连接"}
    except Exception as e:
        return {"success": False, "models": [], "message": f"获取模型列表失败：{e}"}
