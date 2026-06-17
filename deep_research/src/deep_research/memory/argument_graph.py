"""论点-证据图谱 - 显式建模论点和证据的关系。

增强：
- PageRank 风格的重要性评分
- 瓶颈识别（关键证据节点）
- 循环检测（逻辑矛盾）
- 论点强度排序
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import networkx as nx

from ..types import Argument, Evidence, BottleneckNode


class ArgumentGraph:
    """论点-证据图谱。"""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._arguments: dict[str, Argument] = {}
        self._confidence_scores: dict[str, float] = {}

    def add_argument(self, arg: Argument) -> None:
        self._arguments[arg.id] = arg
        self._confidence_scores[arg.id] = arg.confidence
        self.graph.add_node(arg.id, type="argument", stance=arg.stance, confidence=arg.confidence)
        for ev_id in arg.evidence_ids:
            self.graph.add_edge(arg.id, ev_id, relation="supports")
            self.graph.add_node(ev_id, type="evidence")

    def add_evidence(self, ev: Evidence) -> None:
        self.graph.add_node(ev.id, type="evidence", confidence=ev.confidence)
        self._confidence_scores[ev.id] = ev.confidence

    def link_counter(self, arg_a: str, arg_b: str) -> None:
        """记录 arg_a 是对 arg_b 的反驳。"""
        self.graph.add_edge(arg_a, arg_b, relation="counter")

    # ---- 重要性评分（新增）----

    def compute_pagerank(self, damping: float = 0.85, max_iter: int = 100, tol: float = 1e-6) -> dict[str, float]:
        """基于 PageRank 的论点重要性评分。

        核心思想：一个论点被越多高置信度的论点支持，它就越重要。
        通过迭代计算节点的重要性分数，直到收敛。
        """
        if not self.graph.nodes():
            return {}

        # 初始化：所有节点初始分数 = 1/N
        n = len(self.graph.nodes())
        scores = {node: 1.0 / n for node in self.graph.nodes()}

        for _ in range(max_iter):
            new_scores: dict[str, float] = {}
            max_diff = 0.0

            for node in self.graph.nodes():
                # 获取该节点的置信度（作为阻尼因子的一部分）
                base_confidence = self._confidence_scores.get(node, 0.5)

                # 收集所有指向此节点的节点的分数
                incoming = [
                    (pred, data)
                    for pred, succ, data in self.graph.in_edges(node, data=True)
                ]

                if not incoming:
                    # 没有入边的节点（独立论点），只受阻尼影响
                    new_scores[node] = (1 - damping) / n + damping * base_confidence / n
                else:
                    # PageRank 公式 + 置信度加权
                    rank_sum = 0.0
                    for pred, edge_data in incoming:
                        out_degree = max(1, self.graph.out_degree(pred))
                        edge_weight = 1.0 if edge_data.get("relation") == "counter" else 1.0
                        pred_confidence = self._confidence_scores.get(pred, 0.5)
                        rank_sum += scores[pred] * edge_weight * pred_confidence / out_degree

                    new_scores[node] = (1 - damping) / n + damping * rank_sum

                max_diff = max(max_diff, abs(new_scores[node] - scores.get(node, 0.0)))

            scores = new_scores
            if max_diff < tol:
                break

        # 归一化到 0-1
        if scores:
            max_s = max(scores.values())
            if max_s > 0:
                scores = {k: v / max_s for k, v in scores.items()}

        return scores

    # ---- 瓶颈识别（新增）----

    def identify_bottlenecks(self, top_k: int = 5) -> list[BottleneckNode]:
        """识别图中的关键瓶颈节点。

        瓶颈定义：
        1. 依赖度（in_degree）高的证据节点 → 很多论点依赖它
        2. PageRank 分数高 → 重要性大
        3. 没有入边（但有出边）且高 PageRank → 孤立关键节点
        """
        if not self.graph.nodes():
            return []

        pagerank = self.compute_pagerank()

        bottleneck_scores: dict[str, float] = {}
        dependents_count: dict[str, int] = {}

        # 计算每个节点的依赖数量（in_degree = 有多少论点依赖它）
        for node in self.graph.nodes():
            dependents_count[node] = self.graph.in_degree(node)

        # 综合评分：PageRank × 依赖度
        for node, pr_score in pagerank.items():
            dependents = dependents_count.get(node, 0)
            node_type = self.graph.nodes[node].get("type", "unknown")
            # 证据节点依赖度高更重要，论点节点也是
            bottleneck_scores[node] = pr_score * math.log1p(dependents + 1)

        # 找出关键瓶颈（综合评分最高的节点）
        sorted_nodes = sorted(
            bottleneck_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        nodes_info: list[BottleneckNode] = []
        for node_id, score in sorted_nodes:
            node_data = self.graph.nodes[node_id]
            arg = self._arguments.get(node_id)
            stance = (arg.stance if arg else node_data.get("stance", "")) if node_data.get("type") == "argument" else ""
            nodes_info.append(BottleneckNode(
                evidence_id=node_id,
                stance=stance or node_data.get("type", "unknown"),
                importance_score=round(score, 4),
                dependents=dependents_count.get(node_id, 0),
                is_critical=(score > 0.5),
            ))

        return nodes_info

    # ---- 循环检测（新增）----

    def detect_cycles(self) -> list[list[str]]:
        """检测论点图中的循环依赖。

        循环 = 一系列论点互相依赖 → 逻辑矛盾风险。
        返回：所有检测到的循环路径。
        """
        if not self.graph.nodes():
            return []

        try:
            # 使用 NetworkX 的简单环检测（Tarjan 算法）
            cycles = list(nx.simple_cycles(self.graph.to_undirected()))
            # 过滤出只包含论点节点的循环（证据节点在图谱中主要是被引用，不参与循环）
            arg_cycles = [
                [n for n in cycle if self.graph.nodes[n].get("type") == "argument"]
                for cycle in cycles
            ]
            return [c for c in arg_cycles if len(c) >= 2]
        except Exception:
            return []

    # ---- 论点强度排序 ----

    def strongest_arguments(self, top_k: int = 5) -> list[Argument]:
        """返回置信度最高的支持论点。"""
        return sorted(
            self._arguments.values(),
            key=lambda a: a.confidence,
            reverse=True,
        )[:top_k]

    def weakest(self, top_k: int = 5) -> list[Argument]:
        """返回置信度最低的论点（可能需要更多证据）。"""
        return sorted(self._arguments.values(), key=lambda a: a.confidence)[:top_k]

    def rank_by_pagerank(self, top_k: int = 10) -> list[tuple[Argument, float]]:
        """按 PageRank 重要性排序所有论点。"""
        scores = self.compute_pagerank()
        ranked = [
            (arg, scores.get(arg.id, 0.0))
            for arg in self._arguments.values()
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def gaps(self) -> list[str]:
        """识别缺乏证据的论点。"""
        gaps = []
        for arg in self._arguments.values():
            if not arg.evidence_ids:
                gaps.append(f"论点 {arg.id}（{arg.stance[:30]}...）没有任何证据支持")
            elif len(arg.evidence_ids) == 1:
                gaps.append(f"论点 {arg.id}（{arg.stance[:30]}...）只有 1 条证据，单点依赖风险")
        return gaps

    def summary(self) -> dict[str, Any]:
        """生成图谱摘要。"""
        cycles = self.detect_cycles()
        bottlenecks = self.identify_bottlenecks()
        pagerank = self.compute_pagerank()

        return {
            "total_arguments": len(self._arguments),
            "total_nodes": len(self.graph.nodes()),
            "total_edges": len(self.graph.edges()),
            "cycles_detected": len(cycles),
            "cycle_paths": cycles,
            "critical_bottlenecks": [
                {"id": b.evidence_id, "score": b.importance_score, "dependents": b.dependents}
                for b in bottlenecks
            ],
            "top_pagerank": sorted(
                [(n, round(s, 4)) for n, s in pagerank.items() if self.graph.nodes[n].get("type") == "argument"],
                key=lambda x: x[1],
                reverse=True,
            )[:10],
            "evidence_gaps": self.gaps(),
        }

    def export_markdown(self) -> str:
        """导出为 Markdown 摘要。"""
        lines = ["# 论点图谱", ""]
        summary = self.summary()
        lines.append(f"- 论点总数：{summary['total_arguments']}")
        lines.append(f"- 检测到循环：{summary['cycles_detected']} 个")
        lines.append(f"- 关键瓶颈：{len(summary['critical_bottlenecks'])} 个")
        lines.append("")

        for arg, score in self.rank_by_pagerank(10):
            lines.append(f"## {arg.stance}")
            lines.append(f"- PageRank: {score:.4f}")
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
