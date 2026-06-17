"""证据库 - 结构化存储所有 Evidence，支持相似度查询。

增强：
- 冲突检测（相同主题的相反证据）
- 置信度计算（基于来源可靠性 + 交叉验证）
- 影响因子评分（关键证据识别）
- 主题聚类
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from ..types import Evidence, Contradiction


# 来源可靠性权重（可扩展）
SOURCE_RELIABILITY = {
    "arxiv": 0.9,
    "github": 0.7,
    "wikipedia": 0.75,
    "nature.com": 0.95,
    "sciencedirect.com": 0.9,
    "google": 0.6,
    "bing": 0.6,
    "baidu": 0.5,
    "reddit": 0.4,
    "twitter": 0.3,
    "medium": 0.35,
}


class EvidenceStore:
    """证据库 - 内存版（可扩展为 SQLite/向量数据库）。"""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._by_id: dict[str, Evidence] = {}
        self._by_source: dict[str, list[str]] = defaultdict(list)
        self._by_entity: dict[str, list[str]] = defaultdict(list)
        # ---- 新增：主题聚类 ----
        self._by_theme: dict[str, list[str]] = defaultdict(list)
        # ---- 新增：冲突记录 ----
        self._contradictions: dict[str, Contradiction] = {}
        self.persist_path = persist_path
        if persist_path and persist_path.exists():
            self._load()

    # ---- CRUD ----

    def add(self, ev: Evidence) -> None:
        self._by_id[ev.id] = ev
        if ev.source:
            self._by_source[ev.source].append(ev.id)
        # 简单实体识别
        for ent in self._extract_entities(ev.claim):
            self._by_entity[ent.lower()].append(ev.id)
        # 主题聚类（取 claim 中前3个关键词作为主题标签）
        for theme in self._extract_themes(ev.claim):
            self._by_theme[theme.lower()].append(ev.id)
        self._maybe_persist()

    def get(self, ev_id: str) -> Evidence | None:
        return self._by_id.get(ev_id)

    def update(self, ev: Evidence) -> None:
        self._by_id[ev.id] = ev
        self._maybe_persist()

    def all(self) -> list[Evidence]:
        return list(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    # ---- 查询 ----

    def find_related(self, ev: Evidence, top_k: int = 5) -> list[Evidence]:
        """找与 ev 最相关的其他证据（基于来源 + 关键词重合）。"""
        candidates: list[tuple[float, Evidence]] = []
        seen = {ev.id}
        for word in self._extract_entities(ev.claim)[:5]:
            for cand_id in self._by_entity.get(word.lower(), []):
                if cand_id in seen:
                    continue
                seen.add(cand_id)
                cand = self._by_id.get(cand_id)
                if cand is None:
                    continue
                score = self._similarity(ev, cand)
                candidates.append((score, cand))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in candidates[:top_k]]

    def find_counter(self, claim: str, top_k: int = 5) -> list[Evidence]:
        """找反驳某个论点的证据。"""
        # 找带 "[反例]" 标记的，或低 confidence 的
        return [
            ev for ev in self._by_id.values()
            if ev.claim.startswith("[反例]") or ev.confidence < 0.3
        ][:top_k]

    # ---- 冲突检测（新增）----

    def detect_contradictions(self) -> list[Contradiction]:
        """扫描所有证据，检测相互矛盾的证据对。

        策略：
        1. 同主题下 confidence 差异 > 0.5 → 可能冲突
        2. claims 中含否定词（"不是"/"不是"/"无法"/"无效"）→ 疑似相反证据
        3. verified 状态相反 + 高 confidence → 确认冲突
        """
        conflicts: list[Contradiction] = []
        themes = list(self._by_theme.keys())

        for theme in themes:
            ev_ids = self._by_theme.get(theme, [])
            if len(ev_ids) < 2:
                continue

            # 按主题内的 claims 两两对比
            for i, id_a in enumerate(ev_ids):
                ev_a = self._by_id.get(id_a)
                if not ev_a:
                    continue
                for id_b in ev_ids[i + 1:]:
                    ev_b = self._by_id.get(id_b)
                    if not ev_b:
                        continue

                    conflict = self._check_pair_conflict(ev_a, ev_b)
                    if conflict:
                        conflicts.append(conflict)
                        self._contradictions[conflict.id] = conflict

        return conflicts

    def _check_pair_conflict(self, ev_a: Evidence, ev_b: Evidence) -> Contradiction | None:
        """判断两条证据是否冲突。"""
        # 1. 方向检测：claims 中是否有明确的否定关系
        pos_keywords = ["是", "能够", "可以", "有效", "支持", "成立", "优于", "超越", "提升"]
        neg_keywords = ["不是", "不能", "无法", "无效", "不支持", "不成立", "劣于", "不如", "无法提升"]

        def count_direction(claim: str) -> int:
            pos = sum(1 for k in pos_keywords if k in claim)
            neg = sum(1 for k in neg_keywords if k in claim)
            return pos - neg

        dir_a = count_direction(ev_a.claim)
        dir_b = count_direction(ev_b.claim)

        # 方向相反 + 至少一方高置信度 → 潜在冲突
        if dir_a * dir_b < 0 and (ev_a.confidence > 0.5 or ev_b.confidence > 0.5):
            severity = max(ev_a.confidence, ev_b.confidence) * 0.8
            conflict_type = "direct"
            return Contradiction(
                evidence_a=ev_a.id,
                evidence_b=ev_b.id,
                claim_a=ev_a.claim,
                claim_b=ev_b.claim,
                conflict_type=conflict_type,
                severity=severity,
            )

        # 2. 量化差异检测：双方都有量化数据但数值相反
        nums_a = self._extract_numbers(ev_a.claim)
        nums_b = self._extract_numbers(ev_b.claim)
        if nums_a and nums_b:
            # 符号相反（如 "提升了 30%" vs "下降了 20%"）
            if (nums_a[0] > 0 and nums_b[0] < 0) or (nums_a[0] < 0 and nums_b[0] > 0):
                return Contradiction(
                    evidence_a=ev_a.id,
                    evidence_b=ev_b.id,
                    claim_a=ev_a.claim,
                    claim_b=ev_b.claim,
                    conflict_type="statistical",
                    severity=0.7,
                )

        # 3. verified 状态相反
        if ev_a.verified != ev_b.verified and ev_a.confidence > 0.6 and ev_b.confidence > 0.6:
            return Contradiction(
                evidence_a=ev_a.id,
                evidence_b=ev_b.id,
                claim_a=ev_a.claim,
                claim_b=ev_b.claim,
                conflict_type="implication",
                severity=0.6,
            )

        return None

    def get_contradictions(self) -> list[Contradiction]:
        return list(self._contradictions.values())

    def resolve_contradiction(self, conflict_id: str, resolution: str) -> None:
        """解决一个冲突。"""
        if conflict_id in self._contradictions:
            self._contradictions[conflict_id].resolved = True
            self._contradictions[conflict_id].resolution = resolution
            self._maybe_persist()

    # ---- 置信度计算（新增）----

    def compute_confidence(self, ev: Evidence) -> float:
        """综合计算证据置信度。

        公式：
        confidence = base × reliability_weight × verification_bonus × consistency_bonus

        - base: 初始值 0.5
        - reliability_weight: 来源可靠性（0.3-0.95）
        - verification_bonus: 已验证 +0.2，未验证 +0.0
        - consistency_bonus: 与多条相关证据方向一致 +0.1，反之 -0.1
        """
        base = 0.5

        # 来源可靠性
        rel_weight = 0.5
        src_lower = ev.source.lower()
        for domain, weight in SOURCE_RELIABILITY.items():
            if domain in src_lower:
                rel_weight = weight
                break

        # 验证加成
        verification_bonus = 0.2 if ev.verified else 0.0

        # 一致性加成（与同主题证据的方向一致性）
        related = self.find_related(ev, top_k=10)
        if related:
            direction_matches = sum(
                1 for r in related
                if (ev.confidence > 0.5 and r.confidence > 0.5) or
                   (ev.confidence < 0.5 and r.confidence < 0.5)
            )
            consistency_ratio = direction_matches / len(related)
            consistency_bonus = (consistency_ratio - 0.5) * 0.2  # -0.1 ~ +0.1
        else:
            consistency_bonus = 0.0

        confidence = base * rel_weight + verification_bonus + consistency_bonus
        return max(0.0, min(1.0, confidence))

    # ---- 影响因子评分（新增）----

    def compute_impact_scores(self) -> dict[str, float]:
        """计算每条证据的影响因子分数。

        影响因子 = 被引次数 × 置信度 × 独立来源数
        衡量：一条证据被多少其他证据引用、其自身可信度、以及来源多样性。
        """
        # 统计每条证据被 supports 字段引用的次数
        citation_count: dict[str, int] = defaultdict(int)
        for ev in self._by_id.values():
            for supported_id in ev.supports:
                citation_count[supported_id] += 1
            for contradicted_id in ev.contradicts:
                citation_count[contradicted_id] += 1

        scores: dict[str, float] = {}
        for ev in self._by_id.values():
            citations = citation_count.get(ev.id, 0)
            # 来源多样性（相同 source_name 的次数越少越好）
            source_diversity = 1.0 / math.sqrt(max(1, len(self._by_source.get(ev.source, []))))
            scores[ev.id] = (citations + 1) * ev.confidence * (1 + source_diversity)

        # 归一化到 0-1
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                scores = {k: v / max_score for k, v in scores.items()}
        return scores

    def top_impact(self, top_k: int = 10) -> list[Evidence]:
        """返回影响因子最高的证据。"""
        scores = self.compute_impact_scores()
        return sorted(
            [self._by_id[k] for k in scores if k in self._by_id],
            key=lambda e: scores.get(e.id, 0),
            reverse=True,
        )[:top_k]

    # ---- 主题聚类 ----

    def find_by_theme(self, theme: str) -> list[Evidence]:
        """按主题标签查找证据。"""
        ids = self._by_theme.get(theme.lower(), [])
        return [self._by_id[i] for i in ids if i in self._by_id]

    def all_themes(self) -> list[tuple[str, int]]:
        """返回所有主题及其证据数量。"""
        return [(t, len(ids)) for t, ids in self._by_theme.items()]

    # ---- 统计 ----

    def stats(self) -> dict:
        return {
            "total": len(self._by_id),
            "verified": sum(1 for e in self._by_id.values() if e.verified),
            "by_source": {k: len(v) for k, v in self._by_source.items()},
            "avg_confidence": (
                sum(e.confidence for e in self._by_id.values()) / max(1, len(self._by_id))
            ),
            "contradictions": len(self._contradictions),
            "themes": len(self._by_theme),
        }

    # ---- 工具函数 ----

    @staticmethod
    def _extract_entities(claim: str) -> list[str]:
        """简单实体识别：提取连续的中英文词组。"""
        entities: list[str] = []
        # 中文连续字符
        for chunk in re.findall(r'[\u4e00-\u9fff]{2,}', claim):
            entities.append(chunk)
        # 英文单词（>=3字符）
        for word in re.findall(r'[a-zA-Z]{3,}', claim):
            entities.append(word)
        return entities[:8]

    @staticmethod
    def _extract_themes(claim: str) -> list[str]:
        """提取主题标签（取 claim 中最重要的 3 个词）。"""
        # 去掉停用词
        stop = {"的", "是", "在", "和", "了", "与", "或", "对", "为", "有", "这", "那", "a", "an", "the", "is", "are", "and", "or", "of", "to", "in"}
        words = EvidenceStore._extract_entities(claim)
        return [w for w in words if w.lower() not in stop][:3]

    @staticmethod
    def _extract_numbers(claim: str) -> list[float]:
        """提取 claim 中的数字（包括带单位的数值）。"""
        # 提取数字（支持整数、小数、负数、百分数）
        matches = re.findall(r'-?\d+\.?\d*%?', claim)
        nums: list[float] = []
        for m in matches:
            try:
                if m.endswith('%'):
                    nums.append(float(m[:-1]))
                else:
                    nums.append(float(m))
            except ValueError:
                pass
        return nums

    # ---- 持久化 ----

    def _maybe_persist(self) -> None:
        if self.persist_path is None:
            return
        try:
            self.persist_path.write_text(
                json.dumps([e.model_dump(mode="json") for e in self._by_id.values()], ensure_ascii=False)
            )
        except Exception:
            pass

    def _load(self) -> None:
        try:
            data = json.loads(self.persist_path.read_text())
            for d in data:
                ev = Evidence(**d)
                self._by_id[ev.id] = ev
        except Exception:
            pass

    @staticmethod
    def _similarity(a: Evidence, b: Evidence) -> float:
        """简单的 Jaccard 相似度。"""
        wa = set(a.claim.lower().split())
        wb = set(b.claim.lower().split())
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)


def merge_stores(stores: Iterable[EvidenceStore]) -> EvidenceStore:
    """合并多个证据库。"""
    merged = EvidenceStore()
    for s in stores:
        for ev in s.all():
            merged.add(ev)
    return merged
