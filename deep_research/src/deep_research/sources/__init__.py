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
