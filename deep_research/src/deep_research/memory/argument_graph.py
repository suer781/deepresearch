"""论点-证据图谱 - 显式建模论点和证据的关系。

用图结构存储论证关系，替代"把全文塞进上下文"。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx

from ..types import Argument, Evidence


class ArgumentGraph:
    """论点-证据图谱。"""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._arguments: dict[str, Argument] = {}

    def add_argument(self, arg: Argument) -> None:
        self._arguments[arg.id] = arg
        self.graph.add_node(arg.id, type="argument", stance=arg.stance, confidence=arg.confidence)
        for ev_id in arg.evidence_ids:
            self.graph.add_edge(arg.id, ev_id, relation="supports")
            self.graph.add_node(ev_id, type="evidence")

    def add_evidence(self, ev: Evidence) -> None:
        self.graph.add_node(ev.id, type="evidence", confidence=ev.confidence)

    def link_counter(self, arg_a: str, arg_b: str) -> None:
        self.graph.add_edge(arg_a, arg_b, relation="counter")

    def strongest_arguments(self, top_k: int = 5) -> list[Argument]:
        """返回置信度最高的支持论点。"""
        return sorted(
            self._arguments.values(),
            key=lambda a: a.confidence,
            reverse=True,
        )[:top_k]

    def weakest(self, top_k: int = 5) -> list[Argument]:
        return sorted(self._arguments.values(), key=lambda a: a.confidence)[:top_k]

    def gaps(self) -> list[str]:
        """识别缺乏证据的论点。"""
        gaps = []
        for arg in self._arguments.values():
            if not arg.evidence_ids:
                gaps.append(f"论点 {arg.id}（{arg.stance[:30]}...）没有任何证据支持")
        return gaps

    def export_markdown(self) -> str:
        """导出为 Markdown 摘要。"""
        lines = ["# 论点图谱", ""]
        for arg in self.strongest_arguments(10):
            lines.append(f"## {arg.stance}")
            lines.append(f"- 置信度: {arg.confidence:.2f}")
            lines.append(f"- 证据数: {len(arg.evidence_ids)}")
            if arg.counter_argument_ids:
                lines.append(f"- 反论点数: {len(arg.counter_argument_ids)}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arguments": [a.model_dump(mode="json") for a in self._arguments.values()],
            "edges": [{"src": u, "dst": v, **d} for u, v, d in self.graph.edges(data=True)],
        }
