"""
管线工厂 - 组装默认管线实例。

提供 create_default_pipeline() 方法快速创建一条包含
所有标准组件的推荐管线。
"""
from __future__ import annotations

from pipeline.filters import (
    DuplicateFilter,
    LowCredibilityFilter,
    ScamFilter,
    StaleFilter,
)
from pipeline.hydrators import (
    PriceHydrator,
    ProjectHydrator,
    RiskTagHydrator,
    SentimentHydrator,
    VolumeHydrator,
)
from pipeline.orchestrator import PipelineOrchestrator
from pipeline.query_hydration import QueryHydrator
from pipeline.scorers import (
    CredibilityScorer,
    HotnessScorer,
    ImpactScorer,
    RelevanceScorer,
)
from pipeline.selectors import DiversityBlender, WeightedSelector
from pipeline.side_effects import ReportEffect, StorageEffect, TelegramNotifyEffect
from pipeline.sources import (
    KOLSource,
    MarketSource,
    NewsSource,
    OnchainSource,
    RedditSource,
    TwitterSource,
    YouTubeSource,
)


def create_default_pipeline(
    enable_telegram: bool = True,
    enable_storage: bool = True,
    enable_report: bool = True,
    use_diversity_blender: bool = True,
) -> PipelineOrchestrator:
    """
    创建默认推荐管线。

    Args:
        enable_telegram: 是否启用 Telegram 推送副作用
        enable_storage: 是否启用数据库持久化副作用
        enable_report: 是否启用报告生成副作用
        use_diversity_blender: 是否使用多样性混排（否则用纯加权排序）

    Returns:
        配置好所有组件的 PipelineOrchestrator 实例
    """
    orchestrator = PipelineOrchestrator(
        query_hydrator=QueryHydrator(),
        source_timeout=30.0,
        hydrator_timeout=20.0,
    )

    # === Sources ===
    orchestrator.add_source(MarketSource())
    orchestrator.add_source(OnchainSource())
    orchestrator.add_source(TwitterSource())
    orchestrator.add_source(NewsSource())
    orchestrator.add_source(KOLSource())
    orchestrator.add_source(YouTubeSource())
    orchestrator.add_source(RedditSource())

    # === Hydrators（顺序执行，有依赖关系）===
    orchestrator.add_hydrator(PriceHydrator())
    orchestrator.add_hydrator(VolumeHydrator())
    orchestrator.add_hydrator(SentimentHydrator())
    orchestrator.add_hydrator(ProjectHydrator())
    orchestrator.add_hydrator(RiskTagHydrator())

    # === Filters ===
    orchestrator.add_filter(DuplicateFilter())
    orchestrator.add_filter(ScamFilter())
    orchestrator.add_filter(StaleFilter())
    orchestrator.add_filter(LowCredibilityFilter())

    # === Scorers ===
    orchestrator.add_scorer(HotnessScorer())
    orchestrator.add_scorer(CredibilityScorer())
    orchestrator.add_scorer(ImpactScorer())
    orchestrator.add_scorer(RelevanceScorer())

    # === Selector ===
    if use_diversity_blender:
        orchestrator.set_selector(DiversityBlender())
    else:
        orchestrator.set_selector(WeightedSelector())

    # === Side Effects ===
    if enable_telegram:
        orchestrator.add_side_effect(TelegramNotifyEffect(max_items=10, batch_mode=True))
    if enable_storage:
        orchestrator.add_side_effect(StorageEffect())
    if enable_report:
        orchestrator.add_side_effect(ReportEffect())

    return orchestrator
