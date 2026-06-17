"""单元测试 - 证据库。"""
from deep_research.memory.evidence_store import EvidenceStore
from deep_research.types import Evidence


def test_add_and_get():
    s = EvidenceStore()
    ev = Evidence(claim="测试证据", snippet="内容", source="https://x.com")
    s.add(ev)
    assert s.get(ev.id) == ev
    assert len(s) == 1


def test_find_related():
    s = EvidenceStore()
    a = Evidence(claim="5G 技术快速发展", snippet="...", source="x")
    b = Evidence(claim="5G 用户增长", snippet="...", source="y")
    c = Evidence(claim="6G 研究启动", snippet="...", source="z")
    for ev in [a, b, c]:
        s.add(ev)
    related = s.find_related(a, top_k=2)
    assert b in related  # "5G" 关键词重合


def test_stats():
    s = EvidenceStore()
    for i in range(3):
        s.add(Evidence(claim=f"x{i}", snippet="", source=""))
    stats = s.stats()
    assert stats["total"] == 3
