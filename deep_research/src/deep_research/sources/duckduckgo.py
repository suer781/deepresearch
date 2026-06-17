"""DuckDuckGo - 免 key 抓取，多后端。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class DuckDuckGoSource(SearchSource):
    name = "duckduckgo"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=top_k, backend="auto"))
        except Exception:
            return []
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", r.get("url", "")),
                "snippet": r.get("body", ""),
                "source": "duckduckgo",
                "raw": r,
            }
            for r in results
        ]
