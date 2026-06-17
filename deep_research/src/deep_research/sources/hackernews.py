"""Hacker News 搜索 - Algolia 官方 API。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class HackerNewsSource(SearchSource):
    name = "hackernews"
    base = "https://hn.algolia.com/api/v1/search"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            import httpx
        except ImportError:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self.base,
                    params={"query": query, "hitsPerPage": top_k},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return [
                    {
                        "title": h.get("title") or h.get("story_title", ""),
                        "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                        "snippet": h.get("story_text") or h.get("comment_text") or "",
                        "source": "hackernews",
                        "raw": h,
                    }
                    for h in data.get("hits", [])
                ]
        except Exception:
            return []
