"""Tavily 搜索 - AI 原生搜索。"""
from __future__ import annotations

from typing import Any

from ..config import get_settings
from . import SearchSource, register


@register
class TavilySource(SearchSource):
    name = "tavily"

    def __init__(self) -> None:
        self.api_key = get_settings().tavily_api_key
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None and self.api_key:
            try:
                from tavily import AsyncTavilyClient
                self._client = AsyncTavilyClient(api_key=self.api_key)
            except ImportError:
                pass
        return self._client

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return []
        try:
            resp = await client.search(query, max_results=top_k, search_depth="advanced")
        except Exception:
            return []
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "source": "tavily",
                "raw": r,
            }
            for r in resp.get("results", [])
        ]
