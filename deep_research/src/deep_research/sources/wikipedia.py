"""Wikipedia 搜索。"""
from __future__ import annotations

from typing import Any

from . import SearchSource, register


@register
class WikipediaSource(SearchSource):
    name = "wikipedia"

    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            import wikipedia
        except ImportError:
            return []
        try:
            wikipedia.set_lang("zh" if any('\u4e00' <= c <= '\u9fff' for c in query) else "en")
            results = wikipedia.search(query, results=top_k)
            out = []
            for title in results[:top_k]:
                try:
                    page = wikipedia.page(title, auto_suggest=False)
                    out.append({
                        "title": page.title,
                        "url": page.url,
                        "snippet": page.summary[:500],
                        "source": "wikipedia",
                        "raw": {"title": title},
                    })
                except Exception:
                    continue
            return out
        except Exception:
            return []
