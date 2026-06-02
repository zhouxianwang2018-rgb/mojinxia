"""平衡计分卡数据类型定义。所有模块共享的结构契约。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubScore:
    """单个 KPI 评分"""
    name: str
    score: float       # 0-100
    weight: float      # 维度内权重
    detail: str
    raw_value: float


@dataclass
class DimensionScore:
    """维度评分"""
    name: str
    label: str
    weight: float
    score: float
    sub_scores: list[SubScore]
    flags: list[str] = field(default_factory=list)


@dataclass
class Trend:
    """趋势对比"""
    vs_yesterday: Optional[float] = None
    vs_7d_ago: Optional[float] = None
    vs_30d_ago: Optional[float] = None


@dataclass
class ScorecardResult:
    """计分卡完整结果"""
    date: str
    total: float
    grade: str
    dimensions: dict[str, DimensionScore]
    trend: Trend
    anomalies: list[str]
    generated_at: str


def grade_from_score(score: float) -> str:
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"


DIMENSION_WEIGHTS = {
    "returns": 0.40,
    "risk": 0.25,
    "execution": 0.20,
    "evolution": 0.15,
}
