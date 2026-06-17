"""兜底源 - 不存在或未实现时返回空。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class NoopSource(SearchSource):
    name = "noop"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        return []
