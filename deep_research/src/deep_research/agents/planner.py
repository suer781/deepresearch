"""研究规划 Agent - 拆解子问题、选搜索源、排序。"""
from __future__ import annotations

from ..types import AgentRole, EnrichedQuestion, ResearchPlan, SubTask
from .base import BaseAgent


PLANNER_SYSTEM_CLOUD = """你是一个深度研究规划专家。

任务：根据用户的问题，制定一个多智能体并行执行的研究计划。

要求：
1. 拆解为 3-10 个可并行的子任务
2. 每个子任务指定最合适的搜索源（来源名必须从列表中选）
3. 评估总时长
4. 评估是否还需要用户澄清

可选搜索源：
- 国际通用：tavily, brave, exa, searlo, parallel, duckduckgo, bing_scrape, google_scrape
- 学术：arxiv, semantic_scholar, openalex, wikipedia, pubmed
- 代码：github, stackoverflow, npm, pypi
- 社区：hackernews, reddit
- 国内：zhihu, quark_aliyun, baidu_scrape, sogou_scrape, bing_cn_scrape
- 兜底：serpapi, serper

输出严格 JSON：
{
  "rationale": "为什么这样规划",
  "needs_more_clarification": false,
  "clarification_questions": [],
  "sub_tasks": [
    {
      "question": "子问题",
      "preferred_sources": ["tavily", "wikipedia"],
      "parallel": true,
      "priority": 8
    }
  ],
  "estimated_duration_min": 45
}
"""


PLANNER_SYSTEM_LOCAL = PLANNER_SYSTEM_CLOUD.replace(
    "可选搜索源：\n- 国际通用：tavily, brave, exa, searlo, parallel, duckduckgo, bing_scrape, google_scrape\n- 学术：arxiv, semantic_scholar, openalex, wikipedia, pubmed\n- 代码：github, stackoverflow, npm, pypi\n- 社区：hackernews, reddit\n- 国内：zhihu, quark_aliyun, baidu_scrape, sogou_scrape, bing_cn_scrape\n- 兜底：serpapi, serper",
    "【本地部署模式】只能使用以下免 API key 的源：\n- 通用搜索：duckduckgo（强推）\n- 必应抓取：bing_cn_scrape, bing_scrape\n- 通用网页抓取：web_scrape\n- 学术：wikipedia, arxiv, semantic_scholar\n- 代码/社区：github, hackernews, reddit\n\n不要引用任何需要 API key 的源。",
)


class PlannerAgent(BaseAgent):
    role = AgentRole.PLANNER

    def __init__(self, local_mode: bool = False) -> None:
        self.system_prompt = PLANNER_SYSTEM_LOCAL if local_mode else PLANNER_SYSTEM_CLOUD
        self._local_mode = local_mode
        super().__init__()

    async def run(self, eq: EnrichedQuestion) -> ResearchPlan:
        import json
        from ..sources import get_default_sources

        user = json.dumps({
            "mode": "LOCAL (no API keys)" if self._local_mode else "CLOUD",
            "allowed_sources": get_default_sources(local_mode=self._local_mode),
            "background": eq.background,
            "time_frame": eq.time_frame,
            "entities": eq.entities,
            "intent": eq.intent,
            "sub_questions": eq.sub_questions,
            "original": eq.original.text,
        }, ensure_ascii=False)
        result = await self.think_json(user)
        from ..sources import filter_to_local
        sub_tasks = [
            SubTask(
                question=st["question"],
                preferred_sources=filter_to_local(st.get("preferred_sources", [])) if self._local_mode else st.get("preferred_sources", []),
                parallel=st.get("parallel", True),
                priority=st.get("priority", 5),
            )
            for st in result.get("sub_tasks", [])
        ]
        return ResearchPlan(
            enriched_question=eq,
            sub_tasks=sub_tasks,
            estimated_duration_min=result.get("estimated_duration_min", 30),
            rationale=result.get("rationale", ""),
            needs_more_clarification=result.get("needs_more_clarification", False),
            clarification_questions=result.get("clarification_questions", []),
        )
