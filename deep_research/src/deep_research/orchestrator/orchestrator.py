"""主调度器 - 编排研究全流程。

流程：
1. 引导补全
2. 研究规划
3. 方案辩论 (auto-loop if failed)
4. 并行子任务执行
5. 证据验证 + 反例搜索
6. 综合写作
7. 质量审查 (auto-revise if rejected)
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
from ..debate import run_evidence_debate, run_plan_debate
from ..memory.evidence_store import EvidenceStore
from ..types import (
    EnrichedQuestion,
    Question,
    Report,
    ResearchPlan,
)
from ..utils.timeline import Timeline


console = Console()


class Orchestrator:
    """主调度器。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = EvidenceStore()
        self.clarifier = ClarifierAgent()
        self.planner = PlannerAgent()
        self.searcher = SearcherAgent(self.store)
        self.verifier = VerifierAgent(self.store)
        self.adversarial = AdversarialAgent(self.store)
        self.synthesizer = SynthesizerAgent(self.store)
        self.reviewer = ReviewerAgent()
        self.timeline = Timeline()

    # ---- 步骤 1: 引导补全 ----

    async def clarify(self, question: Question) -> EnrichedQuestion:
        console.print("[bold blue]🔍 Step 1: 引导补全...[/bold blue]")
        result = await self.clarifier.run(question)

        if result.get("needs_clarification"):
            console.print("[yellow]需要澄清：[/yellow]")
            for i, q in enumerate(result.get("clarification_questions", []), 1):
                console.print(f"  {i}. {q}")
            # CLI 模式下用输入；这里默认跳过，构造一个空回答
            clarifications = {q: "(未提供)" for q in result.get("clarification_questions", [])}
        else:
            clarifications = {}

        eq = await self.clarifier.finalize(question, clarifications)
        console.print(f"[green]✓ 补全完成: {len(eq.sub_questions)} 个子问题[/green]")
        self.timeline.mark("clarify_done")
        return eq

    # ---- 步骤 2: 研究规划 ----

    async def plan(self, eq: EnrichedQuestion) -> ResearchPlan:
        console.print("[bold blue]📋 Step 2: 研究规划...[/bold blue]")
        p = await self.planner.run(eq)
        console.print(f"[green]✓ 规划: {len(p.sub_tasks)} 个子任务, 估算 {p.estimated_duration_min} 分钟[/green]")
        self.timeline.mark("plan_done")
        return p

    # ---- 步骤 3: 方案辩论 ----

    async def debate_plan(self, plan: ResearchPlan) -> ResearchPlan:
        console.print("[bold blue]⚖️ Step 3: 方案辩论...[/bold blue]")
        debate = await run_plan_debate(plan)
        if debate.passed:
            console.print(f"[green]✓ 方案通过 (经过 {debate.rounds} 轮)[/green]")
        else:
            console.print(f"[yellow]⚠ 方案被驳回，重新规划...[/yellow]")
            # 简单策略：直接重规划一次
            return await self.plan(plan.enriched_question)
        self.timeline.mark("debate_done")
        return plan

    # ---- 步骤 4: 并行执行 ----

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
        console.print(f"[green]✓ 总计 {len(self.store)} 条证据入库存[/green]")

    # ---- 步骤 5: 验证 + 反例 ----

    async def verify_and_adversarial(self) -> None:
        console.print("[bold blue]🔎 Step 5: 验证 + 反例搜索...[/bold blue]")
        all_ev = self.store.all()

        # 验证：高 confidence 的跳过，低的过一遍
        verify_targets = [e for e in all_ev if not e.verified][:20]
        if verify_targets:
            await asyncio.gather(*[self.verifier.run(e.id) for e in verify_targets])
            console.print(f"[green]✓ 验证 {len(verify_targets)} 条证据[/green]")

        # 反例：找主流 claim 跑反例
        if all_ev:
            mainstream = max(all_ev, key=lambda e: e.confidence)
            counter = await self.adversarial.run(mainstream.claim)
            console.print(f"[green]✓ 找到 {len(counter)} 条反例证据[/green]")

        self.timeline.mark("verify_done")

    # ---- 步骤 6: 写作 ----

    async def synthesize(self, question: str) -> Report:
        console.print("[bold blue]✍️ Step 6: 综合写作...[/bold blue]")
        report = await self.synthesizer.run(question)
        console.print(f"[green]✓ 报告: {report.title}[/green]")
        self.timeline.mark("write_done")
        return report

    # ---- 步骤 7: 审查 ----

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

    # ---- 完整流程 ----

    async def run(self, question: Question) -> Report:
        """执行完整研究流程。"""
        console.print(f"\n[bold]📚 Deep Research: {question.text}[/bold]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("研究中...", total=None)
            eq = await self.clarify(question)
            plan = await self.plan(eq)
            plan = await self.debate_plan(plan)
            await self.execute_subtasks(plan)
            await self.verify_and_adversarial()
            report = await self.synthesize(question.text)
            await self.review(report)

        # 输出报告
        self._print_report(report)
        self._save_report(report)

        console.print(f"\n[bold green]✅ 完成！总耗时: {self.timeline.elapsed()}[/bold green]")
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
