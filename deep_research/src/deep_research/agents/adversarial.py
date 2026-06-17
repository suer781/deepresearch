"""反例搜索智能体 - 主动寻找反驳当前论点的证据。"""
from __future__ import annotations

from ..memory.evidence_store import EvidenceStore
from ..sources import get_source
from ..types import AgentRole, Evidence
from .base import BaseAgent


ADVERSARIAL_SYSTEM = """你是"魔鬼代言人"智能体。

任务：故意寻找反驳主流论点的证据。深度研究最大的盲点是确认偏误。

要求：
1. 假设主流观点是错的，构造反向查询
2. 寻找批评、反对、质疑的声音
3. 寻找反例、负面案例、不同立场

输出严格 JSON：
{
  "counter_queries": ["反向查询1", "反向查询2"],
  "counter_evidence": [
    {
      "claim": "反驳论点",
      "snippet": "原文摘要",
      "source_url": "https://...",
      "source_name": "来源",
      "confidence": 0.6
    }
  ]
}
"""


class AdversarialAgent(BaseAgent):
    role = AgentRole.ADVERSARIAL
    system_prompt = ADVERSARIAL_SYSTEM

    def __init__(self, evidence_store: EvidenceStore) -> None:
        super().__init__()
        self.store = evidence_store

    async def run(self, mainstream_claim: str) -> list[Evidence]:
        """针对主流论点，搜索反例。"""
        import asyncio
        import json

        plan = await self.think_json(
            f"主流论点是：{mainstream_claim}\n\n请构造反向搜索查询。"
        )
        queries = plan.get("counter_queries", [f"反对 {mainstream_claim}", f"{mainstream_claim} 失败"])

        async def _search(q: str) -> list[dict]:
            try:
                src = get_source("duckduckgo")
                return await src.search(q, top_k=5)
            except Exception:
                return []

        raw = await asyncio.gather(*[_search(q) for q in queries[:3]])
        flat = [r for chunk in raw for r in chunk]

        if not flat:
            return []

        extract = await self.think_json(
            f"主流论点：{mainstream_claim}\n\n"
            f"反向搜索结果：\n{json.dumps(flat[:20], ensure_ascii=False)}\n\n"
            f"提取反驳证据。"
        )

        evidence_list = []
        for e in extract.get("counter_evidence", []):
            ev = Evidence(
                claim=f"[反例] {e.get('claim', '')}",
                snippet=e.get("snippet", ""),
                source=e.get("source_url", ""),
                source_name=e.get("source_name", ""),
                confidence=e.get("confidence", 0.5),
            )
            self.store.add(ev)
            evidence_list.append(ev)
        return evidence_list
