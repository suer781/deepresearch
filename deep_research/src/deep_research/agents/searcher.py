"""搜索子智能体 - 接收子任务，调用搜索源，返回证据。"""
from __future__ import annotations

from ..memory.evidence_store import EvidenceStore
from ..sources import get_source
from ..types import AgentRole, Evidence, SubTask
from .base import BaseAgent


SEARCHER_SYSTEM = """你是搜索执行智能体。

任务：执行一个具体的研究子任务，调用搜索源，提取有用的证据。

要求：
1. 构造 2-3 个不同角度的搜索查询
2. 从结果中筛选 5-10 条最相关的证据
3. 为每条证据写一句"它支持什么观点"
4. 评估每条证据的可信度（0-1）

输出严格 JSON：
{
  "queries_used": ["query1", "query2"],
  "evidence": [
    {
      "claim": "该证据支持的观点",
      "snippet": "原文摘要（不超过200字）",
      "source_url": "https://...",
      "source_name": "来源名称",
      "confidence": 0.8
    }
  ]
}
"""


class SearcherAgent(BaseAgent):
    role = AgentRole.SEARCHER
    system_prompt = SEARCHER_SYSTEM

    def __init__(self, evidence_store: EvidenceStore, local_mode: bool = False) -> None:
        super().__init__()
        self.store = evidence_store
        self.local_mode = local_mode

    async def run(self, task: SubTask) -> list[Evidence]:
        """执行子任务，搜索并保存证据。"""
        # 步骤 1: 让 LLM 构造查询和提取策略
        from ..sources import filter_to_local, get_default_sources
        preferred = filter_to_local(task.preferred_sources) if self.local_mode else task.preferred_sources
        if not preferred:
            preferred = get_default_sources(local_mode=self.local_mode)[:3]

        plan = await self.think_json(
            f"子问题：{task.question}\n"
            f"可用搜索源（优先顺序）：{preferred}\n\n"
            f"请规划如何搜索这个子问题。"
        )
        queries = plan.get("queries_used", [task.question])

        # 步骤 2: 调用搜索源（异步并行）
        import asyncio
        results_per_query: list[list[dict]] = await asyncio.gather(
            *[_search_with_sources(q, preferred) for q in queries]
        )

        # 步骤 3: 让 LLM 从原始结果中筛选证据
        import json
        raw_combined = []
        for q, results in zip(queries, results_per_query):
            for r in results:
                raw_combined.append({"query": q, **r})

        if not raw_combined:
            return []

        extract = await self.think_json(
            f"子问题：{task.question}\n\n"
            f"原始搜索结果：\n{json.dumps(raw_combined[:30], ensure_ascii=False)}\n\n"
            f"从中筛选 5-10 条最相关的证据。"
        )

        # 步骤 4: 存入证据库
        evidence_list = []
        for e in extract.get("evidence", []):
            ev = Evidence(
                claim=e.get("claim", ""),
                snippet=e.get("snippet", ""),
                source=e.get("source_url", ""),
                source_name=e.get("source_name", ""),
                confidence=e.get("confidence", 0.5),
            )
            self.store.add(ev)
            evidence_list.append(ev)

        return evidence_list


async def _search_with_sources(query: str, preferred: list[str]) -> list[dict]:
    """对一个查询，依次尝试偏好源，合并结果。"""
    import asyncio
    sources_to_try = preferred or ["tavily", "duckduckgo", "wikipedia"]
    results: list[dict] = []

    # 限制并发数
    sem = asyncio.Semaphore(3)

    async def _try(name: str) -> list[dict]:
        async with sem:
            try:
                src = get_source(name)
                return await src.search(query, top_k=5)
            except Exception:
                return []

    out = await asyncio.gather(*[_try(n) for n in sources_to_try[:3]])
    for chunk in out:
        results.extend(chunk)
    return results[:10]
