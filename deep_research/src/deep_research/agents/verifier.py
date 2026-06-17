"""验证智能体 - 交叉验证证据的真实性。"""
from __future__ import annotations

from ..memory.evidence_store import EvidenceStore
from ..types import AgentRole, Evidence
from .base import BaseAgent


VERIFIER_SYSTEM = """你是事实核查专家。

任务：评估一条证据的可信度，识别潜在问题。

核查维度：
1. 来源权威性（官方/媒体/UGC/匿名）
2. 是否与其他证据一致
3. 是否有明显偏见或利益冲突
4. 时效性
5. 一手/二手来源

输出严格 JSON：
{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "notes": "核查说明（50-100字）"
}
"""


class VerifierAgent(BaseAgent):
    role = AgentRole.VERIFIER
    system_prompt = VERIFIER_SYSTEM

    def __init__(self, evidence_store: EvidenceStore) -> None:
        super().__init__()
        self.store = evidence_store

    async def run(self, evidence_id: str) -> Evidence:
        """验证单条证据。"""
        ev = self.store.get(evidence_id)
        if ev is None:
            raise ValueError(f"Evidence {evidence_id} not found")

        related = self.store.find_related(ev, top_k=5)
        related_summary = "\n".join(
            f"- [{r.confidence:.2f}] {r.claim}: {r.snippet}" for r in related
        )

        result = await self.think_json(
            f"待验证证据：\n"
            f"  观点：{ev.claim}\n"
            f"  来源：{ev.source_name or ev.source}\n"
            f"  摘要：{ev.snippet}\n\n"
            f"相关证据：\n{related_summary or '（无）'}\n\n"
            f"请评估这条证据。"
        )

        ev.verified = result.get("verified", False)
        ev.confidence = max(0.0, min(1.0, float(result.get("confidence", ev.confidence))))
        ev.verifier_notes = result.get("notes", "")
        self.store.update(ev)
        return ev
