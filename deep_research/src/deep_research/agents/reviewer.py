"""质量审查智能体 - 检查报告的证据链、覆盖度、潜在盲点。"""
from __future__ import annotations

from ..types import AgentRole, Report
from .base import BaseAgent


REVIEWER_SYSTEM = """你是研究报告质量审查专家。

任务：审查一份报告的质量，识别问题。

审查维度：
1. 证据链：每个关键论断是否有充分证据支持
2. 覆盖度：是否遗漏重要角度
3. 反例：是否考虑了相反证据
4. 时效性：信息是否过时
5. 逻辑：推理是否严密
6. 写作：是否清晰

输出严格 JSON：
{
  "overall_score": 0.0-1.0,
  "issues": [
    {
      "severity": "high/medium/low",
      "category": "evidence/coverage/counter/logic/style",
      "location": "章节名",
      "description": "问题描述"
    }
  ],
  "suggestions": ["改进建议"],
  "approved": true/false
}
"""


class ReviewerAgent(BaseAgent):
    role = AgentRole.REVIEWER
    system_prompt = REVIEWER_SYSTEM

    async def run(self, report: Report) -> dict:
        import json
        report_summary = json.dumps({
            "title": report.title,
            "sections": [
                {"heading": s.get("heading"), "content": s.get("content", "")[:500]}
                for s in report.sections
            ],
            "open_questions": report.open_questions,
            "n_references": len(report.references),
        }, ensure_ascii=False)
        return await self.think_json(
            f"请审查以下报告：\n\n{report_summary}\n\n"
            f"参考文献数量：{len(report.references)}"
        )
