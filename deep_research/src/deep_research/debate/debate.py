"""辩论机制 - 模拟"法庭式"多方辩论。

两种用途：
1. run_plan_debate - 辩论研究方案是否可行
2. run_evidence_debate - 辩论证据是否可信
"""
from __future__ import annotations

from ..agents.base import BaseAgent
from ..config import get_settings
from ..llm import get_llm
from ..types import (
    AgentRole,
    DebatePosition,
    DebateRecord,
    DebateStatement,
    Evidence,
    ResearchPlan,
)


# ---- 角色提示词 ----

PRO_PLAN_SYSTEM = """你是一个研究方案的"正方辩护人"。

任务：论证当前研究方案是合理、可执行的。
要点：
1. 子问题拆解是否合理
2. 搜索源选择是否恰当
3. 并行策略是否高效
4. 估算时长是否现实

请输出严格的 JSON 立场声明。
"""

CON_PLAN_SYSTEM = """你是一个研究方案的"反方批评人"（魔鬼代言人）。

任务：质疑当前研究方案的每一个环节，找漏洞。
要点：
1. 哪些子问题被遗漏
2. 哪些搜索源不适合该问题
3. 时长估算是否过于乐观
4. 哪些地方可能导致死循环或低效

请输出严格的 JSON 立场声明。
"""

PRO_EVIDENCE_SYSTEM = """你是某条证据的"辩护人"。

任务：论证该证据可信、有用。
"""

CON_EVIDENCE_SYSTEM = """你是某条证据的"质疑者"。

任务：质疑该证据的可信度、来源、潜在偏差。
"""

JUDGE_SYSTEM = """你是辩论的"主审法官"。

任务：根据双方辩论，决定：
1. 方案辩论：是否通过
2. 证据辩论：该证据是否采纳

请保持中立，关注论证质量，不站队。
"""


# ---- 通用辩论器 ----

class Debate(BaseAgent):
    """通用辩论。"""

    def __init__(self, topic: str, pro_system: str, con_system: str) -> None:
        super().__init__()
        self.topic = topic
        self.pro_system = pro_system
        self.con_system = con_system
        self.record = DebateRecord(topic=topic)

    async def _argue(self, role_system: str, position: DebatePosition, context: str) -> DebateStatement:
        out = await self.think_json(
            f"辩论主题：{self.topic}\n\n"
            f"当前材料：\n{context}\n\n"
            f"请输出你的立场声明 JSON：\n"
            f'{{"position": "你的核心观点（1-2句）", '
            f'"supporting_points": ["支持点1", "支持点2"], '
            f'"cited_evidence_ids": ["ev-id"]}}'
        )
        return DebateStatement(
            agent_role=AgentRole.DEFENDER if position == DebatePosition.PRO else AgentRole.CRITIC,
            position=position,
            content=out.get("position", ""),
            cited_evidence_ids=out.get("cited_evidence_ids", []),
        )

    async def run(self, context: str, max_rounds: int | None = None) -> DebateRecord:
        max_rounds = max_rounds or get_settings().max_debate_rounds
        for r in range(max_rounds):
            pro = await self._argue(self.pro_system, DebatePosition.PRO, context)
            con = await self._argue(self.con_system, DebatePosition.CON, context)
            self.record.statements.append(pro)
            self.record.statements.append(con)
            self.record.rounds = r + 1

            # 法官裁决是否结束
            judge = await self.llm.think_json(
                system=JUDGE_SYSTEM,
                user=f"辩论主题：{self.topic}\n\n"
                f"正方：{pro.content}\n反方：{con.content}\n\n"
                f"是否已经达成明确结论？输出 JSON：\n"
                f'{{"concluded": true/false, "verdict": "裁决", "passed": true/false}}',
            )
            if judge.get("concluded"):
                self.record.verdict = judge.get("verdict", "")
                self.record.passed = judge.get("passed", False)
                from datetime import datetime
                self.record.concluded_at = datetime.now()
                break
        return self.record


# ---- 预制场景 ----

async def run_plan_debate(plan: ResearchPlan) -> DebateRecord:
    """辩论研究方案是否可行。"""
    context = (
        f"研究问题：{plan.enriched_question.original.text}\n"
        f"背景：{plan.enriched_question.background}\n"
        f"子任务数：{len(plan.sub_tasks)}\n"
        f"子任务：\n" + "\n".join(
            f"  - {st.question} (源: {st.preferred_sources}, 优先级 {st.priority})"
            for st in plan.sub_tasks
        ) + f"\n估算时长：{plan.estimated_duration_min} 分钟"
    )
    d = Debate(
        topic=f"研究方案可行性：{plan.enriched_question.original.text}",
        pro_system=PRO_PLAN_SYSTEM,
        con_system=CON_PLAN_SYSTEM,
    )
    record = await d.run(context)
    return record


async def run_evidence_debate(ev: Evidence, related: list[Evidence]) -> DebateRecord:
    """辩论单条证据是否可信。"""
    context = (
        f"待审证据：\n"
        f"  Claim: {ev.claim}\n  Source: {ev.source_name or ev.source}\n  Snippet: {ev.snippet}\n\n"
        f"相关证据：\n" + "\n".join(
            f"  - {r.claim}: {r.snippet}" for r in related
        )
    )
    d = Debate(
        topic=f"证据 {ev.id} 是否可信",
        pro_system=PRO_EVIDENCE_SYSTEM,
        con_system=CON_EVIDENCE_SYSTEM,
    )
    return await d.run(context, max_rounds=2)
