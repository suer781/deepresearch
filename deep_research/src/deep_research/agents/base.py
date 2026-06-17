"""智能体基类。"""
from __future__ import annotations

import abc
from typing import Any

from ..llm import get_llm
from ..types import AgentRole


class BaseAgent(abc.ABC):
    """所有智能体的基类。"""

    role: AgentRole
    system_prompt: str
    model: str | None = None  # None = 用 primary

    def __init__(self) -> None:
        self.llm = get_llm()

    async def think(self, user_message: str, **kwargs: Any) -> str:
        """单轮对话。"""
        return await self.llm.complete(
            system=self.system_prompt,
            user=user_message,
            model=self.model,
            **kwargs,
        )

    async def think_json(self, user_message: str, **kwargs: Any) -> dict[str, Any]:
        """单轮对话，输出 JSON。"""
        return await self.llm.complete_json(
            system=self.system_prompt,
            user=user_message,
            model=self.model,
            **kwargs,
        )

    @abc.abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """执行智能体任务。"""
        ...
