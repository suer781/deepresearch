"""CLI 入口。"""
from __future__ import annotations

import asyncio
import sys

import click

from .orchestrator import Orchestrator
from .types import Question


@click.command()
@click.argument("question", required=True)
@click.option("--depth", default="normal", type=click.Choice(["shallow", "normal", "deep", "exhaustive"]))
@click.option("--locale", default="zh-CN", help="zh-CN / en-US")
@click.option("--max-parallel", default=8, type=int)
@click.option("--output", "-o", default=None, help="输出 Markdown 报告路径")
def main(question: str, depth: str, locale: str, max_parallel: int, output: str | None) -> None:
    """Deep Research - 超级并行多智能体深度研究系统。"""
    q = Question(text=question, locale=locale, depth_hint=depth)
    orch = Orchestrator()

    if max_parallel:
        from .config import get_settings
        get_settings().max_parallel_subtasks = max_parallel

    try:
        report = asyncio.run(orch.run(q))
    except KeyboardInterrupt:
        click.echo("\n[中断]", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n[错误] {e}", err=True)
        if get_debug():
            raise
        sys.exit(1)

    if output:
        _write_markdown(report, output)
        click.echo(f"\n报告已写入: {output}")


def get_debug() -> bool:
    from .config import get_settings
    return get_settings().debug


def _write_markdown(report, path: str) -> None:
    import json
    from pathlib import Path
    p = Path(path)
    lines = [f"# {report.title}\n", f"**问题**: {report.question}\n"]

    for sec in report.sections:
        lines.append(f"## {sec.get('heading', '')}\n")
        lines.append(sec.get("content", "") + "\n")

    if report.open_questions:
        lines.append("## ⚠️ 未解决问题\n")
        for q in report.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append(f"\n## 📚 参考文献 ({len(report.references)} 条)\n")
    for ev in report.references:
        lines.append(f"- [{ev.confidence:.2f}] {ev.claim} — [{ev.source_name or ev.source}]({ev.source})")

    p.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
