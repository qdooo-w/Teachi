from __future__ import annotations

import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


INSTUCTION = os.getenv("SYSTEM_INSTRUCTION", "")

MODEL_PROVIDER_API_KEY = os.getenv("MODEL_PROVIDER_API_KEY", "")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")


def GetProvider() -> OpenAIChatModel:
    """构建聊天模型实例。"""
    if not MODEL_PROVIDER_API_KEY:
        raise RuntimeError(
            "Missing MODEL_PROVIDER_API_KEY. Please set it in environment variables."
        )

    provider = OpenAIProvider(
        base_url=MODEL_BASE_URL,
        api_key=MODEL_PROVIDER_API_KEY,
    )
    return OpenAIChatModel(
        MODEL_NAME,
        provider=provider,
    )


def GetAgent(
    instructions: str | None = None,
    tools: list | None = None,
    capabilities: list | None = None,
) -> Agent[ChatDeps, str]:
    """创建一个可复用的 Pydantic AI Agent。每次调用都创建新实例，注入工具和能力。"""
    from backend.context import ChatDeps

    return Agent(
        GetProvider(),
        instructions=instructions or INSTUCTION,
        tools=tools or [],
        capabilities=capabilities or [],
        deps_type=ChatDeps,
    )
