"""基础数据类型。

整个系统围绕这些类型流转：
  - Question: 用户原始问题
  - EnrichedQuestion: 引导补全后的问题
  - ResearchPlan: 研究规划
  - Evidence: 单条证据
  - Argument: 论点
  - DebateRecord: 辩论记录
  - Report: 最终报告
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------- 枚举 ----------

class SourceKind(str, Enum):
    """搜索源类型。"""
    WEB_API = "web_api"           # 官方 API (Tavily/Wikipedia/ArXiv...)
    WEB_SCRAPE = "web_scrape"     # 抓取网页 (Bing/Baidu/Sogou...)
    ACADEMIC = "academic"
    CODE = "code"                 # GitHub/StackOverflow
    SOCIAL = "social"             # Reddit/HN
    DOMAIN = "domain"             # 知乎/小红书（需 API）


class AgentRole(str, Enum):
    """智能体角色。"""
    CLARIFIER = "clarifier"           # 引导补全
    PLANNER = "planner"               # 研究规划
    CRITIC = "critic"                 # 方案辩论中的反方
    DEFENDER = "defender"             # 方案辩论中的正方
    SEARCHER = "searcher"             # 搜索子智能体
    READER = "reader"                 # 阅读子智能体
    VERIFIER = "verifier"             # 验证证据真实性
    ADVERSARIAL = "adversarial"       # 反例搜索
    SYNTHESIZER = "synthesizer"       # 综合写作
    REVIEWER = "reviewer"             # 质量审查


# ---------- 输入 ----------

class Question(BaseModel):
    """用户原始问题。"""
    text: str
    locale: str = "zh-CN"
    depth_hint: str | None = None     # "shallow" / "normal" / "deep" / "exhaustive"
    constraints: list[str] = Field(default_factory=list)


class EnrichedQuestion(BaseModel):
    """引导补全后的问题，包含所有必要上下文。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original: Question
    background: str = ""             # 背景
    time_frame: str = ""             # 时间范围
    entities: list[str] = Field(default_factory=list)   # 关键实体
    intent: str = ""                 # 用户的真实意图
    sub_questions: list[str] = Field(default_factory=list)   # 拆解的子问题
    enriched_at: datetime = Field(default_factory=datetime.now)


# ---------- 规划 ----------

class SubTask(BaseModel):
    """一个可并行执行的研究子任务。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str                    # 子问题
    preferred_sources: list[str] = Field(default_factory=list)   # 偏好的搜索源
    parallel: bool = True            # 是否可并行
    priority: int = 5                # 1-10


class ResearchPlan(BaseModel):
    """研究规划。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    enriched_question: EnrichedQuestion
    sub_tasks: list[SubTask]
    estimated_duration_min: int = 0
    rationale: str = ""              # 为什么这样规划
    needs_more_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)


# ---------- 证据 ----------

class Evidence(BaseModel):
    """单条证据 - 整个系统的"硬通货"。

    不依赖上下文，而是带溯源的结构化数据。
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str                       # 证据支持什么观点
    snippet: str                     # 原文片段
    source: str                      # 来源 URL
    source_name: str = ""            # 来源名称（人类可读）
    source_kind: SourceKind = SourceKind.WEB_API
    fetched_at: datetime = Field(default_factory=datetime.now)
    confidence: float = 0.5          # 0-1, 由 verifier 调整
    verified: bool = False
    verifier_notes: str = ""
    contradicts: list[str] = Field(default_factory=list)   # 反驳哪些其他证据
    supports: list[str] = Field(default_factory=list)      # 支持哪些论点


class Argument(BaseModel):
    """论点 - 多个证据的聚合。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stance: str                      # 论点内容
    evidence_ids: list[str]
    confidence: float = 0.5
    counter_argument_ids: list[str] = Field(default_factory=list)


# ---------- 辩论 ----------

class DebatePosition(str, Enum):
    PRO = "pro"
    CON = "con"
    NEUTRAL = "neutral"


class DebateStatement(BaseModel):
    """辩论中的一条发言。"""
    agent_role: AgentRole
    position: DebatePosition
    content: str
    cited_evidence_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class DebateRecord(BaseModel):
    """一次完整辩论的记录。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str                       # 辩论主题
    statements: list[DebateStatement] = Field(default_factory=list)
    verdict: str = ""                # 最终裁决
    passed: bool = False             # 方案辩论是否通过
    rounds: int = 0
    concluded_at: datetime | None = None


# ---------- 报告 ----------

class Report(BaseModel):
    """最终输出报告。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    question: str
    sections: list[dict[str, Any]] = Field(default_factory=list)   # [{heading, content, evidence_ids}]
    references: list[Evidence] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)       # 未解决的疑点
    confidence_overall: float = 0.5
    generated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
