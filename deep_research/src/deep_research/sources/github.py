"""GitHub 公开 API 搜索。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class GitHubSource(SearchSource):
    name = "github"
    base = "https://api.github.com/search/repositories"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            import httpx
        except ImportError:
            return []
        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"Accept": "application/vnd.github.v3+json"},
            ) as client:
                resp = await client.get(
                    self.base,
                    params={"q": query, "per_page": top_k},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return [
                    {
                        "title": r.get("full_name", ""),
                        "url": r.get("html_url", ""),
                        "snippet": (r.get("description") or "")[:500],
                        "source": "github",
                        "raw": r,
                    }
                    for r in data.get("items", [])
                ]
        except Exception:
            return []
