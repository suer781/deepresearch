"""LLM 客户端 - 统一 OpenAI 兼容接口。"""
from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from .config import get_settings


class LLMClient:
    """统一的 LLM 客户端，支持结构化输出、JSON 模式、流式。"""

    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncOpenAI(
            api_key=s.openai_api_key or "sk-placeholder",
            base_url=s.openai_base_url,
        )
        self.primary = s.primary_model
        self.debater = s.debater_model
        self.critic = s.critic_model

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """简单文本补全。"""
        model = model or self.primary
        resp = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """JSON 模式补全，失败时尝试解析。"""
        text = await self.complete(
            system,
            user + "\n\n请以严格 JSON 格式输出，不要包含 markdown 代码块。",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # 尝试从 markdown 代码块中提取
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到 JSON 片段
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
