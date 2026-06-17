"""证据库 - 结构化存储所有 Evidence，支持相似度查询。

这是"破解信息裁剪"的核心：所有证据都持久化在外部存储，
智能体之间通过 evidence_id 引用，而不是靠上下文传递全文。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from ..types import Evidence


class EvidenceStore:
    """证据库 - 内存版（可扩展为 SQLite/向量数据库）。"""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._by_id: dict[str, Evidence] = {}
        self._by_source: dict[str, list[str]] = defaultdict(list)
        self._by_entity: dict[str, list[str]] = defaultdict(list)
        self.persist_path = persist_path
        if persist_path and persist_path.exists():
            self._load()

    # ---- CRUD ----

    def add(self, ev: Evidence) -> None:
        self._by_id[ev.id] = ev
        if ev.source:
            self._by_source[ev.source].append(ev.id)
        for ent in ev.claim.split()[:5]:  # 简单实体识别
            self._by_entity[ent.lower()].append(ev.id)
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
        for word in ev.claim.split()[:5]:
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
        # 简化：找带 "[反例]" 标记的，或低 confidence 的
        return [
            ev for ev in self._by_id.values()
            if ev.claim.startswith("[反例]") or ev.confidence < 0.3
        ][:top_k]

    def stats(self) -> dict:
        return {
            "total": len(self._by_id),
            "verified": sum(1 for e in self._by_id.values() if e.verified),
            "by_source": {k: len(v) for k, v in self._by_source.items()},
            "avg_confidence": (
                sum(e.confidence for e in self._by_id.values()) / max(1, len(self._by_id))
            ),
        }

    # ---- 持久化（可选） ----

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
