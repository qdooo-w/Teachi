from __future__ import annotations

import asyncio
import os

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from pathlib import Path
from typing import Callable

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
INSTUCTION = load_instruction()

MODEL_PROVIDER_API_KEY = os.getenv("MODEL_PROVIDER_API_KEY", "")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")

# 测试连接默认超时时间（秒）
TEST_CONNECTION_TIMEOUT = 15


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
) -> dict:
    """测试模型 API 连通性。

    发送一个极简请求（max_tokens=1）来验证 API Key、Base URL 和模型名称是否有效。
    返回 {"success": bool, "message": str, "model": str | None}。
    """
    try:
        model = GetProvider(api_key=api_key, base_url=base_url, model_name=model_name)
        # 使用 openai 异步客户端发送极简请求，避免 pydantic-ai Agent 的复杂依赖
        # 注意：max_tokens 不能设太小，部分模型（如思考模型）有最低 token 限制
        client = model.client  # AsyncOpenAI 客户端
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model.model_name,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=64,
            ),
            timeout=TEST_CONNECTION_TIMEOUT,
        )
        # 能走到这里说明连接成功
        return {
            "success": True,
            "message": "Connection successful",
            "model": model.model_name,
        }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": f"Connection timed out after {TEST_CONNECTION_TIMEOUT} seconds. Please check your Base URL and network.",
            "model": None,
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "model": None,
        }
