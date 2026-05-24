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


def load_prompt(filename: str) -> Callable[[], str]:
    """返回一个从 backend/config/prompts/<filename> 读取提示词的函数。"""
    def _loader() -> str:
        path = Path(__file__).parent / "prompts" / filename
        return path.read_text(encoding="utf-8")
    return _loader


# 保留常量以兼容现有引用
INSTUCTION = load_instruction()

MODEL_PROVIDER_API_KEY = os.getenv("MODEL_PROVIDER_API_KEY", "")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")

# 测试连接默认超时时间（秒）
TEST_CONNECTION_TIMEOUT = 15


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
