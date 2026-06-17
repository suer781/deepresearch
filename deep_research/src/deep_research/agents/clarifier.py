"""引导补全 Agent - 负责把含糊问题变成结构化 EnrichedQuestion。"""
from __future__ import annotations

import json

from ..types import AgentRole, EnrichedQuestion, Question
from .base import BaseAgent


CLARIFIER_SYSTEM = """你是一个研究问题补全专家。

你的任务：把用户含糊的问题补全为研究可用的结构化信息。

要求：
1. 识别问题中的歧义、时间范围不明确、关键实体缺失
2. 用对话方式向用户询问最多 3 个关键问题（不要罗嗦）
3. 如果问题已经足够清晰，直接生成补全结果

输出严格 JSON：
{
  "needs_clarification": true/false,
  "clarification_questions": ["问题1", "问题2"],
  "background": "问题背景（已知信息）",
  "time_frame": "涉及的时间范围",
  "entities": ["关键实体1", "关键实体2"],
  "intent": "用户真实意图",
  "sub_questions": ["拆解的子问题1", "子问题2", "子问题3"]
}
"""


class ClarifierAgent(BaseAgent):
    role = AgentRole.CLARIFIER
    system_prompt = CLARIFIER_SYSTEM

    async def run(self, question: Question) -> dict:
        """分析问题，返回补全结果。

        第一阶段：只返回澄清问题。
        用户回答后，第二阶段调用 finalize 生成 EnrichedQuestion。
        """
        user = f"用户问题：{question.text}\n\n约束：{question.constraints}"
        return await self.think_json(user)

    async def finalize(
        self, question: Question, clarifications: dict[str, str]
    ) -> EnrichedQuestion:
        """根据用户澄清回答，生成最终 EnrichedQuestion。"""
        user = json.dumps({
            "original_question": question.text,
            "user_clarifications": clarifications,
        }, ensure_ascii=False)
        result = await self.think_json(user)
        eq = EnrichedQuestion(
            original=question,
            background=result.get("background", ""),
            time_frame=result.get("time_frame", ""),
            entities=result.get("entities", []),
            intent=result.get("intent", ""),
            sub_questions=result.get("sub_questions", [question.text]),
        )
        return eq
