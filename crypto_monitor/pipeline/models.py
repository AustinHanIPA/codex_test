"""
Pipeline 核心领域模型。

定义贯穿整条推荐管线的数据结构：
- ContentItem: 单条信息内容（新闻、KOL观点、链上异动等）
- UserProfile: 用户画像（关注币种、风险偏好、历史行为）
- PipelineContext: 单次管线执行的上下文
- PipelineResult: 管线最终输出
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ContentType(str, Enum):
    """内容类型枚举。"""
    NEWS = "news"
    KOL_OPINION = "kol_opinion"
    ONCHAIN_ALERT = "onchain_alert"
    PRICE_MOVEMENT = "price_movement"
    RISK_WARNING = "risk_warning"
    YOUTUBE_VIDEO = "youtube_video"
    REDDIT_POST = "reddit_post"
    TWITTER_POST = "twitter_post"


class RiskLevel(str, Enum):
    """风险偏好级别。"""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class ContentItem:
    """
    单条内容项 - 在整条管线中流转的核心数据单元。

    从 Source 层产出，经过 Hydrator 补充元数据、Filter 过滤、
    Scorer 打分，最后由 Selector 选入推荐结果集。
    """
    # === 身份标识 ===
    content_id: str
    content_type: ContentType
    source: str  # e.g. "twitter", "reddit", "onchain", "news"

    # === 主体内容 ===
    title: str = ""
    body: str = ""
    url: str = ""
    author: str = ""
    author_followers: int = 0

    # === 关联币种 ===
    symbols: List[str] = field(default_factory=list)

    # === 时间 ===
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = field(default_factory=datetime.now)

    # === Hydrator 补充的元数据 ===
    price_change_percent: Optional[float] = None
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    sentiment: Optional[str] = None  # bullish / bearish / neutral
    sentiment_score: Optional[float] = None  # -1.0 ~ 1.0
    project_background: Optional[str] = None
    risk_tags: List[str] = field(default_factory=list)

    # === Scorer 打分结果 ===
    score_hotness: float = 0.0       # 热度分
    score_credibility: float = 0.0   # 可信度分
    score_impact: float = 0.0        # 潜在影响分
    score_relevance: float = 0.0     # 用户兴趣匹配分
    score_final: float = 0.0         # 综合得分

    # === Filter 标记 ===
    is_duplicate: bool = False
    is_scam: bool = False
    is_stale: bool = False
    is_low_credibility: bool = False
    filtered: bool = False
    filter_reason: str = ""

    # === 原始数据 ===
    raw: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "content_id": self.content_id,
            "content_type": self.content_type.value,
            "source": self.source,
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "author": self.author,
            "symbols": self.symbols,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "price_change_percent": self.price_change_percent,
            "volume_24h": self.volume_24h,
            "sentiment": self.sentiment,
            "risk_tags": self.risk_tags,
            "score_hotness": round(self.score_hotness, 3),
            "score_credibility": round(self.score_credibility, 3),
            "score_impact": round(self.score_impact, 3),
            "score_relevance": round(self.score_relevance, 3),
            "score_final": round(self.score_final, 3),
            "filtered": self.filtered,
            "filter_reason": self.filter_reason,
        }


@dataclass
class UserProfile:
    """
    用户画像。

    Query Hydration 层的核心输入，用于个性化推荐。
    """
    user_id: str = "default"

    # 关注的币种列表
    watch_symbols: List[str] = field(default_factory=list)

    # 风险偏好
    risk_preference: RiskLevel = RiskLevel.MODERATE

    # 关注的内容类型
    preferred_content_types: List[ContentType] = field(default_factory=list)

    # 历史点击/交互记录 (content_id -> timestamp)
    click_history: List[Dict[str, Any]] = field(default_factory=list)

    # 用户标签
    tags: List[str] = field(default_factory=list)

    # 已展示过的 content_id 集合，用于去重
    seen_content_ids: Set[str] = field(default_factory=set)

    # 黑名单来源
    blocked_sources: List[str] = field(default_factory=list)

    # 黑名单币种
    blocked_symbols: List[str] = field(default_factory=list)


@dataclass
class PipelineContext:
    """
    单次管线执行的上下文。

    在管线各层之间传递状态和配置。
    """
    # 本次请求的主题/查询
    query: str = ""
    topic_symbols: List[str] = field(default_factory=list)

    # 用户画像（经 Query Hydration 后）
    user_profile: UserProfile = field(default_factory=UserProfile)

    # 管线配置参数
    max_items: int = 20
    diversity_ratio: float = 0.3  # 混排多样性比例

    # 执行过程中的状态
    started_at: Optional[datetime] = field(default_factory=datetime.now)
    source_counts: Dict[str, int] = field(default_factory=dict)
    filter_stats: Dict[str, int] = field(default_factory=dict)
    stage_timings: Dict[str, float] = field(default_factory=dict)

    # 额外配置
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """
    管线最终输出。
    """
    # 推荐结果
    items: List[ContentItem] = field(default_factory=list)

    # 元信息
    context: Optional[PipelineContext] = None
    total_sourced: int = 0
    total_after_filter: int = 0
    total_selected: int = 0

    # 执行时间
    duration_ms: float = 0.0
    generated_at: Optional[datetime] = field(default_factory=datetime.now)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.as_dict() for item in self.items],
            "total_sourced": self.total_sourced,
            "total_after_filter": self.total_after_filter,
            "total_selected": self.total_selected,
            "duration_ms": round(self.duration_ms, 2),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "source_counts": self.context.source_counts if self.context else {},
            "filter_stats": self.context.filter_stats if self.context else {},
        }
