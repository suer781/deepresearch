"""辩论机制。"""
from .debate import (
    Debate,
    run_plan_debate,
    run_evidence_debate,
    analyze_plan_weaknesses,
    score_debate_strength,
)

__all__ = [
    "Debate",
    "run_plan_debate",
    "run_evidence_debate",
    "analyze_plan_weaknesses",
    "score_debate_strength",
]
