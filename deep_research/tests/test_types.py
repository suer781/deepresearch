"""单元测试 - 类型。"""
from deep_research.types import (
    AgentRole,
    DebatePosition,
    EnrichedQuestion,
    Evidence,
    Question,
    ResearchPlan,
    SubTask,
)


def test_question_to_enriched():
    q = Question(text="研究 5G 发展")
    eq = EnrichedQuestion(
        original=q,
        background="5G 商用 5 年",
        time_frame="2019-2026",
        entities=["5G", "中国", "运营商"],
        intent="评估 5G 现状与未来",
        sub_questions=["5G 用户数", "5G 覆盖率"],
    )
    assert len(eq.sub_questions) == 2
    assert eq.entities == ["5G", "中国", "运营商"]


def test_evidence_creation():
    ev = Evidence(
        claim="5G 用户突破 10 亿",
        snippet="据工信部...",
        source="https://example.com",
    )
    assert ev.confidence == 0.5
    assert not ev.verified
    assert ev.id  # 自动生成


def test_subtask_creation():
    st = SubTask(
        question="测试",
        preferred_sources=["tavily", "wikipedia"],
        priority=8,
    )
    assert st.priority == 8
    assert st.parallel is True
