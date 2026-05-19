"""
Scorers 层 - 为内容打分。

- HotnessScorer: 热度分
- CredibilityScorer: 可信度分
- ImpactScorer: 潜在影响分
- RelevanceScorer: 用户兴趣匹配分
"""
from pipeline.scorers.hotness_scorer import HotnessScorer
from pipeline.scorers.credibility_scorer import CredibilityScorer
from pipeline.scorers.impact_scorer import ImpactScorer
from pipeline.scorers.relevance_scorer import RelevanceScorer

__all__ = [
    "HotnessScorer",
    "CredibilityScorer",
    "ImpactScorer",
    "RelevanceScorer",
]
