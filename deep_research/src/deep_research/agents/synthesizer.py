"""综合写作智能体 - 把证据库组织成可发表级报告。"""
from __future__ import annotations

from ..memory.evidence_store import EvidenceStore
from ..types import AgentRole, Report
from .base import BaseAgent


SYNTHESIZER_SYSTEM = """你是深度研究写作专家。

任务：基于证据库，生成一份结构清晰、论证严密的研究报告。

要求：
1. 标题简洁有力
2. 章节按"总-分-总"结构组织
3. 每个关键论断必须有证据 ID 引用
4. 标注证据置信度
5. 列出"未解决问题"和"局限性"
6. 文风：严谨但不枯燥，避免营销腔

输出严格 JSON：
{
  "title": "报告标题",
  "sections": [
    {
      "heading": "章节标题",
      "content": "章节内容（Markdown格式），用 [证据ID] 标注引用",
      "evidence_ids": ["ev-id-1", "ev-id-2"]
    }
  ],
  "open_questions": ["未解决问题1"],
  "confidence_overall": 0.0-1.0
}
"""


class SynthesizerAgent(BaseAgent):
    role = AgentRole.SYNTHESIZER
    system_prompt = SYNTHESIZER_SYSTEM

    def __init__(self, evidence_store: EvidenceStore) -> None:
        super().__init__()
        self.store = evidence_store

    async def run(self, question: str) -> Report:
        all_ev = self.store.all()
        if not all_ev:
            return Report(title=question, question=question, confidence_overall=0.0)

        # 按主题聚类（这里简单按 sources 维度组织）
        evidence_summary = "\n".join(
            f"[{ev.id}] (conf={ev.confidence:.2f}, src={ev.source_name or ev.source})\n"
            f"  Claim: {ev.claim}\n  Evidence: {ev.snippet}"
            for ev in all_ev[:80]  # 防止超长
        )

        result = await self.think_json(
            f"研究问题：{question}\n\n"
            f"证据库（{len(all_ev)} 条）：\n{evidence_summary}\n\n"
            f"请生成最终报告。"
        )

        return Report(
            title=result.get("title", question),
            question=question,
            sections=result.get("sections", []),
            references=all_ev,
            open_questions=result.get("open_questions", []),
            confidence_overall=result.get("confidence_overall", 0.5),
        )
