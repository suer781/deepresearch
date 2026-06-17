"""主调度器 - 编排研究全流程。

增强（相比 v0.x）：
1. 多轮反思循环（ReAct 风格）：每轮生成 → 行动 → 反思 → 决定下一步
2. 矛盾检测：收集完证据后自动检测冲突证据
3. 迭代改进：报告生成后进行自我反思，识别遗漏并重新执行
4. 辩论强度评分：记录辩论的攻击力/防御力/深度
5. 图谱瓶颈识别：识别关键证据节点
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..agents import (
    AdversarialAgent,
    ClarifierAgent,
    PlannerAgent,
    ReviewerAgent,
    SearcherAgent,
    SynthesizerAgent,
    VerifierAgent,
)
from ..config import get_settings
from ..debate import analyze_plan_weaknesses, run_evidence_debate, run_plan_debate, score_debate_strength
from ..memory.argument_graph import ArgumentGraph
from ..memory.evidence_store import EvidenceStore
from ..types import (
    EnrichedQuestion,
    Question,
    ReflectionRound,
    Report,
    ResearchPlan,
)
from ..utils.timeline import Timeline


console = Console()

# 反思问题模板（用于 ReAct 循环）
REFLECTION_QUESTIONS = [
    "当前研究遗漏了什么重要信息？",
    "有哪些相反的证据或观点我没有考虑？",
    "现有证据的置信度是否足够支撑结论？",
    "是否有被检测到的矛盾需要解决？",
]


class Orchestrator:
    """主调度器（增强版）。"""

    def __init__(self, local_mode: bool | None = None) -> None:
        self.settings = get_settings()
        self.local_mode = local_mode if local_mode is not None else self.settings.use_local_model
        if self.local_mode:
            self.settings.use_local_model = True
        self.store = EvidenceStore()
        self.argument_graph = ArgumentGraph()
        self.clarifier = ClarifierAgent()
        self.planner = PlannerAgent(local_mode=self.local_mode)
        self.searcher = SearcherAgent(self.store, local_mode=self.local_mode)
        self.verifier = VerifierAgent(self.store)
        self.adversarial = AdversarialAgent(self.store, local_mode=self.local_mode)
        self.synthesizer = SynthesizerAgent(self.store)
        self.reviewer = ReviewerAgent()
        self.timeline = Timeline()
        # 反思历史
        self.reflection_history: list[ReflectionRound] = []
        # 最大反思轮数（防止无限循环）
        self.max_reflection_rounds = 3

    # ---- 步骤 0: ReAct 反思循环（新增）----

    async def _reflect(self, round_num: int, context: str) -> ReflectionRound:
        """执行一轮反思（ReAct 的 "Reflect" 阶段）。

        问自己：
        1. 遗漏了什么？
        2. 矛盾冲突有哪些？
        3. 置信度是否足够？
        """
        reflection = ReflectionRound(
            round=round_num,
            question="; ".join(REFLECTION_QUESTIONS),
            answer="",
            gaps=[],
            suggested_actions=[],
        )

        # 用 LLM 做反思
        prompt = (
            f"你正在研究一个问题。以下是当前研究状态：\n{context}\n\n"
            f"请反思以下 {len(REFLECTION_QUESTIONS)} 个问题：\n"
            + "\n".join(f"  {i+1}. {q}" for i, q in enumerate(REFLECTION_QUESTIONS)) + "\n\n"
            f"输出严格 JSON：\n"
            f'{{"answer": "综合回答（100-300字）", '
            f'"gaps": ["缺口1", "缺口2"], '
            f'"suggested_actions": ["建议行动1", "建议行动2"], '
            f'"iteration_needed": true/false}}'
        )

        try:
            from ..agents.base import BaseAgent
            agent = BaseAgent()
            result = await agent.think_json(prompt)
            reflection.answer = result.get("answer", "")
            reflection.gaps = result.get("gaps", [])
            reflection.suggested_actions = result.get("suggested_actions", [])
            reflection.iteration_needed = result.get("iteration_needed", False)
        except Exception as e:
            console.print(f"[dim]反思 LLM 调用失败（使用默认回答）: {e}[/dim]")
            reflection.answer = "反思执行失败，继续下一阶段。"

        self.reflection_history.append(reflection)
        console.print(f"[dim]反思第 {round_num} 轮: 识别到 {len(reflection.gaps)} 个缺口[/dim]")
        return reflection

    # ---- 步骤 1: 引导补全 ----

    async def clarify(self, question: Question) -> EnrichedQuestion:
        console.print("[bold blue]🔍 Step 1: 引导补全...[/bold blue]")
        result = await self.clarifier.run(question)

        if result.get("needs_clarification"):
            console.print("[yellow]需要澄清：[/yellow]")
            for i, q in enumerate(result.get("clarification_questions", []), 1):
                console.print(f"  {i}. {q}")
            clarifications = {q: "(未提供)" for q in result.get("clarification_questions", [])}
        else:
            clarifications = {}

        eq = await self.clarifier.finalize(question, clarifications)
        console.print(f"[green]✓ 补全完成: {len(eq.sub_questions)} 个子问题[/green]")
        self.timeline.mark("clarify_done")
        return eq

    # ---- 步骤 2: 研究规划 + 弱点分析（增强）----

    async def plan(self, eq: EnrichedQuestion) -> ResearchPlan:
        console.print("[bold blue]📋 Step 2: 研究规划...[/bold blue]")
        p = await self.planner.run(eq)

        # 增强：先做弱点分析
        try:
            weakness = await analyze_plan_weaknesses(p)
            if weakness:
                issues = weakness.get("overall_weak", [])[:3]
                if issues:
                    console.print(f"[yellow]⚠ 方案弱点检测: {', '.join(issues)}[/yellow]")
                completeness = weakness.get("completeness_score", 5)
                if completeness < 5:
                    console.print(f"[yellow]⚠ 完整性评分过低: {completeness}/10，建议补充子问题[/yellow]")
        except Exception:
            pass

        console.print(f"[green]✓ 规划: {len(p.sub_tasks)} 个子任务, 估算 {p.estimated_duration_min} 分钟[/green]")
        self.timeline.mark("plan_done")
        return p

    # ---- 步骤 3: 方案辩论 + 强度评分（增强）----

    async def debate_plan(self, plan: ResearchPlan) -> ResearchPlan:
        console.print("[bold blue]⚖️ Step 3: 方案辩论...[/bold blue]")
        debate = await run_plan_debate(plan)

        # 增强：计算辩论强度
        strength = score_debate_strength(debate)
        console.print(
            f"[dim]辩论强度: 攻击 {strength['attack_score']:.2f} "
            f"| 防御 {strength['defense_score']:.2f} "
            f"| 深度 {strength['depth_score']:.2f} "
            f"| 综合 {strength['overall_score']:.2f}[/dim]"
        )

        if debate.passed:
            console.print(f"[green]✓ 方案通过 (经过 {debate.rounds} 轮)[/green]")
        else:
            console.print(f"[yellow]⚠ 方案被驳回，重新规划...[/yellow]")
            return await self.plan(plan.enriched_question)

        self.timeline.mark("debate_done")
        return plan

    # ---- 步骤 4: 并行执行 + 矛盾检测（增强）----

    async def execute_subtasks(self, plan: ResearchPlan) -> None:
        console.print(f"[bold blue]🚀 Step 4: 并行执行 {len(plan.sub_tasks)} 个子任务...[/bold blue]")
        sem = asyncio.Semaphore(self.settings.max_parallel_subtasks)

        async def _run_with_sem(task):
            async with sem:
                console.print(f"  → {task.question[:60]}...")
                evs = await self.searcher.run(task)
                console.print(f"    [green]✓ 获得 {len(evs)} 条证据[/green]")
                return evs

        await asyncio.gather(*[_run_with_sem(t) for t in plan.sub_tasks])
        self.timeline.mark("search_done")

        # 增强：收集完后自动做矛盾检测
        if len(self.store) > 1:
            console.print("[bold blue]🔎 步骤 4b: 矛盾检测...[/bold blue]")
            contradictions = self.store.detect_contradictions()
            if contradictions:
                console.print(f"[yellow]⚠ 检测到 {len(contradictions)} 对矛盾证据:[/yellow]")
                for c in contradictions[:3]:
                    console.print(
                        f"  - [{c.conflict_type}] "
                        f"ev_a: {c.claim_a[:50]}... ↔ "
                        f"ev_b: {c.claim_b[:50]}... (severity={c.severity:.2f})"
                    )
            else:
                console.print("[green]✓ 未检测到矛盾[/green]")

        console.print(f"[green]✓ 总计 {len(self.store)} 条证据入库存[/green]")

        # 增强：计算影响因子
        impact_scores = self.store.compute_impact_scores()
        top_ids = sorted(impact_scores, key=impact_scores.get, reverse=True)[:5]
        if top_ids:
            console.print(f"[dim]高影响因子证据: {', '.join(k[:8] for k in top_ids)}[/dim]")

    # ---- 步骤 5: 验证 + 反例 + 图谱分析（增强）----

    async def verify_and_adversarial(self) -> None:
        console.print("[bold blue]🔎 Step 5: 验证 + 反例搜索...[/bold blue]")
        all_ev = self.store.all()

        # 验证：按置信度分层
        verify_targets = [e for e in all_ev if not e.verified][:20]
        if verify_targets:
            await asyncio.gather(*[self.verifier.run(e.id) for e in verify_targets])
            console.print(f"[green]✓ 验证 {len(verify_targets)} 条证据[/green]")

        # 反例：找主流 claim 跑反例
        if all_ev:
            mainstream = max(all_ev, key=lambda e: e.confidence)
            counter = await self.adversarial.run(mainstream.claim)
            console.print(f"[green]✓ 找到 {len(counter)} 条反例证据[/green]")

        # 增强：把证据加入论点图谱，做瓶颈分析
        self._build_argument_graph()
        bottlenecks = self.argument_graph.identify_bottlenecks(top_k=3)
        if bottlenecks:
            console.print(f"[yellow]⚠ 识别到 {len(bottlenecks)} 个关键瓶颈:[/yellow]")
            for b in bottlenecks:
                if b.is_critical:
                    console.print(f"  🔴 {b.evidence_id[:8]}... | 重要性 {b.importance_score:.3f} | 被 {b.dependents} 个论点依赖")

        # 增强：循环检测
        cycles = self.argument_graph.detect_cycles()
        if cycles:
            console.print(f"[yellow]⚠ 检测到 {len(cycles)} 个逻辑循环，请检查论点链:[/yellow]")

        self.timeline.mark("verify_done")

    def _build_argument_graph(self) -> None:
        """把证据库构建为论点图谱。"""
        all_ev = self.store.all()
        for ev in all_ev:
            self.argument_graph.add_evidence(ev)

    # ---- 步骤 6: 写作 + 自我反思（增强）----

    async def synthesize(self, question: str) -> Report:
        console.print("[bold blue]✍️ Step 6: 综合写作...[/bold blue]")

        # 增强：把图谱分析结果注入写作上下文
        graph_summary = ""
        if self.argument_graph.graph.nodes():
            try:
                graph_summary = self.argument_graph.export_markdown()[:1000]
            except Exception:
                pass

        # 获取高影响证据
        top_evidence = self.store.top_impact(top_k=10)
        evidence_context = ""
        if top_evidence:
            evidence_context = "\n高影响因子证据（优先引用）：\n" + "\n".join(
                f"- [{ev.id[:8]}] (conf={ev.confidence:.2f}) {ev.claim[:80]}"
                for ev in top_evidence
            )

        # 获取未解决的矛盾
        unresolved = [c for c in self.store.get_contradictions() if not c.resolved]
        conflict_context = ""
        if unresolved:
            conflict_context = "\n⚠️ 未解决的矛盾证据对（需在报告中讨论）：\n" + "\n".join(
                f"- {c.claim_a[:50]} ↔ {c.claim_b[:50]}"
                for c in unresolved[:3]
            )

        report = await self.synthesizer.run(
            question,
            extra_context=graph_summary + evidence_context + conflict_context,
        )
        console.print(f"[green]✓ 报告: {report.title}[/green]")
        self.timeline.mark("write_done")
        return report

    # ---- 步骤 7: 审查 + 反思循环（增强）----

    async def review(self, report: Report) -> Report:
        console.print("[bold blue]🔍 Step 7: 质量审查...[/bold blue]")
        review = await self.reviewer.run(report)
        score = review.get("overall_score", 0.5)
        console.print(f"  评分: {score:.2f}, 通过: {review.get('approved', False)}")
        if review.get("issues"):
            for issue in review["issues"][:3]:
                console.print(f"  - [{issue.get('severity', '?')}] {issue.get('description', '')}")
        self.timeline.mark("review_done")
        return report

    async def _rethink(self, report: Report, round_num: int) -> bool:
        """反思报告，决定是否需要重新生成。

        返回 True = 需要重新生成。
        """
        issues = []
        try:
            from ..agents.base import BaseAgent
            agent = BaseAgent()
            # 构建反思上下文
            context = (
                f"报告标题: {report.title}\n"
                f"证据库统计: {json.dumps(self.store.stats())}\n"
                f"参考文献数: {len(report.references)}\n"
                f"未解决问题: {len(report.open_questions)}\n"
            )
            prompt = (
                f"以下是研究报告摘要，请判断是否需要重新生成：\n{context}\n\n"
                f"输出严格 JSON：\n"
                f'{{"needs_regeneration": true/false, "reasons": ["原因1"], "missing_aspects": ["遗漏方面"]}}'
            )
            result = await agent.think_json(prompt)
            needs = result.get("needs_regeneration", False)
            if needs:
                issues = result.get("missing_aspects", [])
        except Exception:
            pass

        if issues:
            console.print(f"[yellow]⚠ 反思第 {round_num} 轮: 识别到 {len(issues)} 个遗漏[/yellow]")
            for issue in issues[:3]:
                console.print(f"  - {issue}")
            return True
        return False

    # ---- 完整流程（增强：多轮反思循环）----

    async def run(self, question: Question) -> Report:
        """执行完整研究流程（增强版：多轮反思循环）。

        流程：
        ┌─────────────────────────────────────────┐
        │  Loop (最多 max_reflection_rounds 轮)     │
        │  ┌───────────────────────────────────┐  │
        │  │ 1. 引导补全                        │  │
        │  │ 2. 研究规划 + 弱点分析              │  │
        │  │ 3. 方案辩论 + 强度评分              │  │
        │  │ 4. 并行执行 + 矛盾检测              │  │
        │  │ 5. 验证 + 反例 + 图谱瓶颈识别      │  │
        │  │ 6. 综合写作 + 自我反思              │  │
        │  │ 7. 质量审查                        │  │
        │  │ → 反思: 遗漏了什么？               │  │
        │  │ → 决定: 继续下一轮 or 结束         │  │
        │  └───────────────────────────────────┘  │
        └─────────────────────────────────────────┘
        """
        console.print(f"\n[bold]📚 Deep Research: {question.text}[/bold]")
        if self.local_mode:
            from ..llm import get_llm
            llm = get_llm()
            console.print(f"[dim]🏠 本地模式: model={llm.primary or 'local'}, endpoint={llm.base_url}, 仅免 key 搜索源[/dim]")
        else:
            console.print("[dim]☁️ 云端模式[/dim]")

        report: Report | None = None

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("研究中...", total=None)

            # 多轮反思循环
            for round_num in range(1, self.max_reflection_rounds + 1):
                if round_num > 1:
                    console.print(f"\n[bold cyan]🔄 反思循环第 {round_num} 轮[/bold cyan]")

                eq = await self.clarify(question)
                plan = await self.debate_plan(plan=await self.plan(eq))
                await self.execute_subtasks(plan)
                await self.verify_and_adversarial()
                report = await self.synthesize(question.text)
                await self.review(report)

                # 反思：判断是否需要继续
                if round_num < self.max_reflection_rounds:
                    reflection = await self._reflect(
                        round_num,
                        context=f"报告: {report.title}\n参考文献: {len(report.references)}\n"
                                f"未解决问题: {len(report.open_questions)}\n"
                                f"置信度: {report.confidence_overall:.2f}",
                    )
                    if not reflection.iteration_needed:
                        console.print("[green]✓ 反思判定：质量已足够，结束[/green]")
                        break
                    # 有缺口 → 但已经做了 max_rounds，跳出
                    console.print(f"[yellow]继续反思循环（第 {round_num}/{self.max_reflection_rounds}）[/yellow]")
                else:
                    console.print("[yellow]达到最大反思轮数，结束[/yellow]")

        # 输出报告
        if report:
            self._print_report(report)
            self._save_report(report)

        console.print(f"\n[bold green]✅ 完成！总耗时: {self.timeline.elapsed()}[/bold green]")
        if self.reflection_history:
            console.print(f"[dim]反思历史: {len(self.reflection_history)} 轮[/dim]")
        return report

    def _print_report(self, report: Report) -> None:
        console.print("\n" + "=" * 80)
        console.print(f"[bold]{report.title}[/bold]")
        console.print("=" * 80)
        for sec in report.sections:
            console.print(f"\n## {sec.get('heading', '')}")
            console.print(sec.get("content", ""))
        if report.open_questions:
            console.print("\n## ⚠️ 未解决问题")
            for q in report.open_questions:
                console.print(f"- {q}")
        console.print(f"\n## 📚 参考文献 ({len(report.references)} 条)")
        for ev in report.references[:20]:
            console.print(f"- [{ev.confidence:.2f}] {ev.claim[:80]} - {ev.source_name or ev.source}")

    def _save_report(self, report: Report) -> None:
        out_dir = self.settings.storage_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{report.id}.json"
        out.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        console.print(f"\n[dim]报告已保存: {out}[/dim]")
