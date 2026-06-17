"""阅读子智能体 - 抓取并精读单个网页，提取深层信息。"""
from __future__ import annotations

from ..memory.evidence_store import EvidenceStore
from ..types import AgentRole, Evidence
from .base import BaseAgent


READER_SYSTEM = """你是网页精读专家。

任务：阅读给定网页的完整内容，提取比搜索摘要更深入的信息。

要求：
1. 提取关键事实、数据、引语
2. 识别论证逻辑
3. 标注不确定/有争议的部分
4. 输出多条精炼证据

输出严格 JSON：
{
  "summary": "页面核心内容（2-3 句）",
  "evidence": [
    {
      "claim": "该页面支持的观点",
      "snippet": "关键原文（30-100字）",
      "confidence": 0.7
    }
  ]
}
"""


class ReaderAgent(BaseAgent):
    role = AgentRole.READER
    system_prompt = READER_SYSTEM

    def __init__(self, evidence_store: EvidenceStore) -> None:
        super().__init__()
        self.store = evidence_store

    async def run(self, url: str, context_question: str) -> list[Evidence]:
        """阅读一个网页。"""
        from ..sources import get_source
        scrape = get_source("web_scrape")
        try:
            text = await scrape.fetch_full_text(url)
        except Exception as e:
            return []

        if not text:
            return []

        # 截断过长文本
        text = text[:8000]

        result = await self.think_json(
            f"研究问题：{context_question}\n\n"
            f"网页 URL：{url}\n\n"
            f"网页内容：\n{text}\n\n"
            f"请精读并提取证据。"
        )

        evidence_list = []
        for e in result.get("evidence", []):
            ev = Evidence(
                claim=e.get("claim", ""),
                snippet=e.get("snippet", ""),
                source=url,
                confidence=e.get("confidence", 0.5),
            )
            self.store.add(ev)
            evidence_list.append(ev)
        return evidence_list
