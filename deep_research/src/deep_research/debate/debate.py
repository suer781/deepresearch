"""辩论机制 - 模拟"法庭式"多方辩论。

增强：
- 多轮反驳链（不是简单的来回，而是逐点反驳链）
- 方案弱点定位（每个子问题/搜索源/时长的具体评分）
- 辩论强度评分（论点攻击力、防御力、综合分）
- 法官裁决量化（每个维度的通过阈值）
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

# ---- 辩论弱点定位提示词（新增）----
WEAKNESS_ANALYZER_SYSTEM = """你是研究方案的"弱点诊断专家"。

任务：对研究方案的每个维度（子问题、搜索源、时长估算）给出弱点评分。

评分维度（每项 0-10 分，越低越有问题）：
1. 完整性：是否遗漏了重要子问题？
2. 匹配度：搜索源是否最适合这些问题？
3. 时效性：时长估算是否合理？
4. 冗余性：是否有重复或无效的子任务？

请输出严格 JSON：
{
  "completeness_score": 0-10,
  "source_match_score": 0-10,
  "time_estimate_score": 0-10,
  "redundancy_score": 0-10,
  "overall_weak": ["具体弱点1", "具体弱点2"],
  "critical_gaps": ["关键缺口1"],
  "suggested_fixes": ["修复建议1"]
}
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

    async def _argue(
        self,
        role_system: str,
        position: DebatePosition,
        context: str,
        opponent_statement: str = "",
    ) -> DebateStatement:
        """单轮辩论发言，支持对上一轮的反驳内容。"""
        prompt = f"辩论主题：{self.topic}\n\n当前材料：\n{context}\n"
        if opponent_statement:
            prompt += f"\n对方立场（需要你反驳）：\n{opponent_statement}\n"

        prompt += "\n请输出你的立场声明 JSON：\n"
        prompt += '{"position": "你的核心观点（1-2句）", "supporting_points": ["支持点1", "支持点2"], "cited_evidence_ids": ["ev-id"], "rebuttal_to": "对方立场的具体弱点（1句）"}'

        out = await self.think_json(prompt)
        return DebateStatement(
            agent_role=AgentRole.DEFENDER if position == DebatePosition.PRO else AgentRole.CRITIC,
            position=position,
            content=out.get("position", ""),
            cited_evidence_ids=out.get("cited_evidence_ids", []),
        )

    async def run(
        self,
        context: str,
        max_rounds: int | None = None,
        track_rebuttals: bool = True,
    ) -> DebateRecord:
        """运行多轮辩论，支持反驳链。

        辩论流程：
        Round 1: pro 发言 → con 发言 → 法官初判
        Round 2+: pro 针对 con 的弱点反驳 → con 针对 pro 的防御反驳 → 法官裁决
        ...
        直到法官认为结论明确或达到最大轮数。
        """
        max_rounds = max_rounds or get_settings().max_debate_rounds
        pro_prev = ""
        con_prev = ""

        for r in range(max_rounds):
            # 正方发言（Round 2+ 时针对反方上一轮的反驳）
            pro = await self._argue(
                self.pro_system,
                DebatePosition.PRO,
                context,
                opponent_statement=con_prev if r > 0 else "",
            )
            self.record.statements.append(pro)

            # 反方发言（Round 2+ 时针对正方上一轮的反驳）
            con = await self._argue(
                self.con_system,
                DebatePosition.CON,
                context,
                opponent_statement=pro_prev if r > 0 else "",
            )
            self.record.statements.append(con)

            self.record.rounds = r + 1
            pro_prev = pro.content
            con_prev = con.content

            # 法官裁决是否结束
            judge = await self.llm.think_json(
                system=JUDGE_SYSTEM,
                user=f"辩论主题：{self.topic}\n\n"
                     f"第 {r+1} 轮：\n正方：{pro.content}\n反方：{con.content}\n\n"
                     f"是否已经达成明确结论？输出 JSON：\n"
                     f'{{"concluded": true/false, "verdict": "裁决说明", "passed": true/false, "confidence": 0-1}}',
            )
            if judge.get("concluded"):
                self.record.verdict = judge.get("verdict", "")
                self.record.passed = judge.get("passed", False)
                from datetime import datetime
                self.record.concluded_at = datetime.now()
                break

        return self.record


# ---- 辩论强度评分（新增）----

def score_debate_strength(record: DebateRecord) -> dict:
    """对辩论记录做强度评分。

    评分维度：
    - attack_score: 反方攻击力（反驳是否具体、有证据支撑）
    - defense_score: 正方防御力（反驳是否有效回应了反方）
    - depth_score: 辩论深度（轮数越多、论点越深入）
    - overall_score: 综合分
    """
    if not record.statements:
        return {"attack_score": 0, "defense_score": 0, "depth_score": 0, "overall_score": 0}

    # 按轮次分组
    pros = [s for s in record.statements if s.position == DebatePosition.PRO]
    cons = [s for s in record.statements if s.position == DebatePosition.CON]

    # 攻击评分：反方发言长度 + 是否引用了证据
    if cons:
        avg_con_len = sum(len(s.content) for s in cons) / len(cons)
        con_cited = sum(len(s.cited_evidence_ids) for s in cons)
        attack_score = min(1.0, (avg_con_len / 500) * 0.5 + (con_cited / 3) * 0.5)
    else:
        attack_score = 0.0

    # 防御评分：正方回应了多少反方的质疑
    if pros:
        avg_pro_len = sum(len(s.content) for s in pros) / len(pros)
        pro_cited = sum(len(s.cited_evidence_ids) for s in pros)
        defense_score = min(1.0, (avg_pro_len / 500) * 0.5 + (pro_cited / 3) * 0.5)
    else:
        defense_score = 0.0

    # 深度评分：轮数越多越深
    depth_score = min(1.0, record.rounds / 5)

    overall_score = (attack_score * 0.3 + defense_score * 0.4 + depth_score * 0.3)
    return {
        "attack_score": round(attack_score, 3),
        "defense_score": round(defense_score, 3),
        "depth_score": round(depth_score, 3),
        "overall_score": round(overall_score, 3),
        "passed": record.passed,
        "rounds": record.rounds,
    }


# ---- 弱点分析（新增）----

async def analyze_plan_weaknesses(plan: ResearchPlan) -> dict:
    """对研究方案做弱点分析，给出每个维度的评分。"""
    context = (
        f"研究问题：{plan.enriched_question.original.text}\n"
        f"背景：{plan.enriched_question.background}\n"
        f"子任务数：{len(plan.sub_tasks)}\n"
        f"子任务：\n" + "\n".join(
            f"  - {st.question} (源: {st.preferred_sources}, 优先级 {st.priority})"
            for st in plan.sub_tasks
        ) + f"\n估算时长：{plan.estimated_duration_min} 分钟"
    )

    from ..agents.base import BaseAgent
    agent = BaseAgent()
    result = await agent.think_json(f"请分析以下研究方案的弱点：\n\n{context}")
    return result


# ---- 预制场景 ----

async def run_plan_debate(plan: ResearchPlan) -> DebateRecord:
    """辩论研究方案是否可行（支持多轮反驳链）。"""
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
