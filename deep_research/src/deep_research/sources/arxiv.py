"""ArXiv 学术搜索。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class ArxivSource(SearchSource):
    name = "arxiv"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            import arxiv
        except ImportError:
            return []
        try:
            search = arxiv.Search(
                query=query,
                max_results=top_k,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            client = arxiv.Client()
            results = []
            for paper in client.results(search):
                results.append({
                    "title": paper.title,
                    "url": paper.entry_id,
                    "snippet": paper.summary[:500],
                    "source": "arxiv",
                    "raw": {
                        "authors": [a.name for a in paper.authors],
                        "published": paper.published.isoformat(),
                    },
                })
            return results
        except Exception:
            return []
