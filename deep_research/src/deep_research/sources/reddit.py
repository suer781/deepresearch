"""Reddit 公开 JSON 抓取（免认证）。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class RedditSource(SearchSource):
    name = "reddit"
    base = "https://www.reddit.com/search.json"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            import httpx
        except ImportError:
            return []
        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": "DeepResearch/1.0"},
            ) as client:
                resp = await client.get(
                    self.base,
                    params={"q": query, "limit": top_k, "sort": "relevance"},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return [
                    {
                        "title": c["data"].get("title", ""),
                        "url": "https://reddit.com" + c["data"].get("permalink", ""),
                        "snippet": c["data"].get("selftext", "")[:500],
                        "source": "reddit",
                        "raw": c["data"],
                    }
                    for c in data.get("data", {}).get("children", [])
                ]
        except Exception:
            return []
