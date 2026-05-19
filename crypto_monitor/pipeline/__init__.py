"""
Crypto Monitor Pipeline - 推荐式信息流架构

整体流程:
    用户/主题请求
        ↓
    Query Hydration: 补用户关注币种、风险偏好、历史点击
        ↓
    Sources: Twitter/X, YouTube, Reddit, 新闻, 链上数据, KOL 发言
        ↓
    Hydrators: 补价格变化、补成交量、补情绪、补项目方背景、补风险标签
        ↓
    Filters: 去重、过滤诈骗币、过滤旧闻、过滤低可信来源
        ↓
    Scorers: 热度分、可信度分、潜在影响分、用户兴趣匹配分
        ↓
    Selector / Blender: 新闻、链上异动、KOL观点、风险提醒混排
        ↓
    Side Effects: 记录已展示内容、收集用户点击反馈、更新下一次推荐
"""

from pipeline.models import ContentItem, UserProfile, PipelineContext, PipelineResult
from pipeline.orchestrator import PipelineOrchestrator
from pipeline.factory import create_default_pipeline

__all__ = [
    "ContentItem",
    "UserProfile",
    "PipelineContext",
    "PipelineResult",
    "PipelineOrchestrator",
    "create_default_pipeline",
]
