"""搜索沙箱 — 多搜索引擎并行检索，超时隔离，失败不阻塞。

把所有搜索源（ddgs / bing_scrape / wikipedia / arxiv 等）用统一的
async 沙箱管理。每一个源独立：
  - 有自己的超时
  - 失败不影响别的源
  - 统一返回结构给上层 Agent

类似浏览器里"同时开 N 个标签页搜不同引擎"。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from .sources import get_source


# 搜索引擎白名单（沙箱里可用的源，本地部署模式下只用这些免 API key 的）
SANDBOX_SOURCES_DEFAULT: list[str] = [
    "duckduckgo",
    "bing_cn_scrape",
    "bing_scrape",
    "wikipedia",
    "arxiv",
    "semantic_scholar",
    "hackernews",
    "reddit",
    "github",
]


@dataclass
class SearchResultItem:
    """单条搜索结果（标准化）。"""
    title: str
    url: str
    snippet: str
    source: str           # 源名
    raw: dict | None = None
    fetched_at: float = field(default_factory=time.time)


@dataclass
class SearchSourceResult:
    """一个源的搜索结果（可能成功也可能失败）。"""
    source: str
    ok: bool
    items: list[SearchResultItem] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None


@dataclass
class SandboxRun:
    """一次完整的并行搜索会话。"""
    query: str
    top_k_per_source: int = 5
    per_source_timeout_sec: int = 15
    sources: list[str] = field(default_factory=lambda: list(SANDBOX_SOURCES_DEFAULT))
    results: list[SearchSourceResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def total_items(self) -> int:
        return sum(len(r.items) for r in self.results)

    @property
    def successful_sources(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed_sources(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    def dedup_items(self, max_total: int = 50) -> list[SearchResultItem]:
        """按 URL 去重，截断总条数。"""
        seen = set()
        out: list[SearchResultItem] = []
        for r in self.results:
            for item in r.items:
                key = item.url.lower().strip()
                if key in seen or not key:
                    continue
                seen.add(key)
                out.append(item)
                if len(out) >= max_total:
                    return out
        return out

    def to_agent_format(self) -> list[dict]:
        """给上层 Agent 消费的格式（类似原来 list[dict]）。"""
        return [
            {
                "title": it.title,
                "url": it.url,
                "snippet": it.snippet,
                "source": it.source,
            }
            for it in self.dedup_items()
        ]


class SearchSandbox:
    """搜索引擎沙箱管理器。

    用法：
        sb = SearchSandbox()
        run = await sb.search("深度研究：xxx", sources=["duckduckgo", "wikipedia"])
        # run.results 里每个 SearchSourceResult 独立成功/失败
        # run.to_agent_format() 给 Agent 消费
    """

    def __init__(
        self,
        default_sources: list[str] | None = None,
        top_k_per_source: int = 5,
        per_source_timeout_sec: int = 15,
    ) -> None:
        self.default_sources = default_sources or list(SANDBOX_SOURCES_DEFAULT)
        self.top_k_per_source = top_k_per_source
        self.per_source_timeout_sec = per_source_timeout_sec
        # 缓存：同一 query 在短时间内不再重复搜索
        self._cache: dict[str, SandboxRun] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_ttl_sec = 600

    async def search(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        top_k_per_source: int | None = None,
        per_source_timeout_sec: int | None = None,
        bypass_cache: bool = False,
    ) -> SandboxRun:
        """并行执行 N 个搜索引擎。"""
        sources = sources or self.default_sources
        top_k = top_k_per_source or self.top_k_per_source
        per_src_timeout = per_source_timeout_sec or self.per_source_timeout_sec

        cache_key = f"{query.lower().strip()}||{','.join(sources)}||{top_k}"
        if not bypass_cache:
            async with self._cache_lock:
                cached = self._cache.get(cache_key)
                if cached and (time.time() - cached.started_at) < self._cache_ttl_sec:
                    return cached

        run = SandboxRun(
            query=query,
            top_k_per_source=top_k,
            per_source_timeout_sec=per_src_timeout,
            sources=sources,
        )

        # 并行：每个源独立的 async 任务
        tasks = [
            self._run_single_source(src_name, query, top_k, per_src_timeout)
            for src_name in sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        run.results = list(results)

        # 存入缓存
        async with self._cache_lock:
            self._cache[cache_key] = run

        return run

    async def _run_single_source(
        self,
        source_name: str,
        query: str,
        top_k: int,
        timeout_sec: int,
    ) -> SearchSourceResult:
        start = time.time()
        try:
            src = get_source(source_name)
            # 给每个源独立超时
            raw_items = await asyncio.wait_for(
                src.search(query, top_k=top_k),
                timeout=timeout_sec,
            )

            items = [
                SearchResultItem(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    source=source_name,
                    raw=r.get("raw"),
                )
                for r in raw_items
                if r.get("url")
            ]
            return SearchSourceResult(
                source=source_name,
                ok=True,
                items=items,
                duration_ms=(time.time() - start) * 1000,
            )
        except asyncio.TimeoutError:
            return SearchSourceResult(
                source=source_name,
                ok=False,
                error=f"timeout after {timeout_sec}s",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return SearchSourceResult(
                source=source_name,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def fetch_full_texts(
        self,
        urls: list[str],
        *,
        per_url_timeout_sec: int = 20,
        max_parallel: int = 4,
    ) -> list[dict]:
        """抓取一组 URL 的正文内容（Reader Agent 用）。"""
        sem = asyncio.Semaphore(max_parallel)

        async def _fetch(url: str) -> dict:
            async with sem:
                try:
                    src = get_source("web_scrape")
                    text = await asyncio.wait_for(
                        src.fetch_full_text(url),
                        timeout=per_url_timeout_sec,
                    )
                    return {"url": url, "ok": True, "text": text[:8000]}
                except Exception as e:
                    return {"url": url, "ok": False, "error": str(e)}

        return await asyncio.gather(*[_fetch(u) for u in urls])

    def summarize(self, run: SandboxRun) -> str:
        """人类可读的摘要。"""
        lines = [
            f"查询: {run.query}",
            f"源: {len(run.sources)} (成功 {run.successful_sources}, 失败 {run.failed_sources})",
            f"结果: {run.total_items} 条",
        ]
        for r in run.results:
            if r.ok:
                lines.append(f"  ✅ {r.source}: {len(r.items)} 条 ({r.duration_ms:.0f}ms)")
            else:
                lines.append(f"  ❌ {r.source}: {r.error} ({r.duration_ms:.0f}ms)")
        return "\n".join(lines)


# 全局单例沙箱
_SHARED_SANDBOX: SearchSandbox | None = None


def get_sandbox() -> SearchSandbox:
    global _SHARED_SANDBOX
    if _SHARED_SANDBOX is None:
        _SHARED_SANDBOX = SearchSandbox()
    return _SHARED_SANDBOX


__all__ = [
    "SANDBOX_SOURCES_DEFAULT",
    "SearchResultItem",
    "SearchSourceResult",
    "SandboxRun",
    "SearchSandbox",
    "get_sandbox",
]
