"""Semantic Scholar - 学术搜索。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class SemanticScholarSource(SearchSource):
    name = "semantic_scholar"
    base = "https://api.semanticscholar.org/graph/v1/paper/search"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            import httpx
        except ImportError:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self.base,
                    params={
                        "query": query,
                        "limit": top_k,
                        "fields": "title,abstract,url,year,authors",
                    },
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return [
                    {
                        "title": p.get("title", ""),
                        "url": p.get("url", ""),
                        "snippet": (p.get("abstract") or "")[:500],
                        "source": "semantic_scholar",
                        "raw": p,
                    }
                    for p in data.get("data", [])
                ]
        except Exception:
            return []
