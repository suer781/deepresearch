"""搜索源抽象 + 工厂。"""
from __future__ import annotations

import abc
from typing import Any


class SearchSource(abc.ABC):
    """搜索源基类。"""

    name: str

    @abc.abstractmethod
    async def search(self, query: str, *, top_k: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        """执行搜索，返回标准化结果列表。

        每条结果格式：
        {
          "title": "...",
          "url": "...",
          "snippet": "...",
          "source": "源名",
          "raw": {...}  # 原始数据
        }
        """
        ...

    async def fetch_full_text(self, url: str) -> str:
        """抓取 URL 完整文本（默认实现：搜索引擎可直接抓）。"""
        raise NotImplementedError


# 全局注册表
_REGISTRY: dict[str, type[SearchSource]] = {}
_INSTANCES: dict[str, SearchSource] = {}


def register(cls: type[SearchSource]) -> type[SearchSource]:
    """类装饰器：注册搜索源。"""
    _REGISTRY[cls.name] = cls
    return cls


def get_source(name: str) -> SearchSource:
    """获取搜索源单例。"""
    if name in _INSTANCES:
        return _INSTANCES[name]
    if name not in _REGISTRY:
        # 兜底：返回 noop
        from .noop import NoopSource
        return NoopSource()
    inst = _REGISTRY[name]()
    _INSTANCES[name] = inst
    return inst


def available_sources() -> list[str]:
    return list(_REGISTRY.keys())


# 免 API key / 纯本地可部署的源
LOCAL_PREFERRED = [
    "duckduckgo",     # 免 key 抓取
    "bing_cn_scrape",  # 免 key 抓取
    "bing_scrape",     # 免 key 抓取
    "web_scrape",      # 通用抓取
    "wikipedia",       # 公开媒体 API
    "arxiv",           # 公开 API
    "semantic_scholar",  # 公开 API
    "hackernews",      # 公开 Algolia API
    "reddit",          # 公开 JSON endpoint
    "github",          # 匿名（有限速率）
]


def get_local_sources() -> list[str]:
    """返回当前已注册且免 key 的源列表。"""
    return [n for n in LOCAL_PREFERRED if n in _REGISTRY]


def get_default_sources(local_mode: bool = False) -> list[str]:
    """根据模式返回默认搜索源优先级。"""
    if local_mode:
        return get_local_sources()
    # 云端模式：Tavily/Exa 等优先，但 ddgs/wikipedia 也带上兜底
    ordered = ["tavily", "exa", "duckduckgo", "wikipedia", "arxiv",
               "semantic_scholar", "hackernews", "reddit", "github",
               "bing_cn_scrape", "bing_scrape", "web_scrape"]
    return [n for n in ordered if n in _REGISTRY]


def filter_to_local(sources: list[str]) -> list[str]:
    """强制过滤到本地白名单。如果结果为空就给一套兜底。"""
    whitelist = set(get_local_sources())
    kept = [s for s in sources if s in whitelist]
    if kept:
        return kept
    return ["duckduckgo", "wikipedia", "web_scrape"]


# 触发所有源注册
def _import_all() -> None:
    from . import (  # noqa: F401
        tavily,
        duckduckgo,
        wikipedia,
        arxiv,
        bing,
        semantic_scholar,
        hackernews,
        reddit,
        github,
        noop,
    )


_import_all()
