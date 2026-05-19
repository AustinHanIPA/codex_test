"""
Hydrators 层 - 为内容项补充元数据。

- PriceHydrator: 补充价格变化数据
- VolumeHydrator: 补充成交量信息
- SentimentHydrator: 补充情绪分析
- ProjectHydrator: 补充项目方背景
- RiskTagHydrator: 补充风险标签
"""
from pipeline.hydrators.price_hydrator import PriceHydrator
from pipeline.hydrators.volume_hydrator import VolumeHydrator
from pipeline.hydrators.sentiment_hydrator import SentimentHydrator
from pipeline.hydrators.project_hydrator import ProjectHydrator
from pipeline.hydrators.risk_tag_hydrator import RiskTagHydrator

__all__ = [
    "PriceHydrator",
    "VolumeHydrator",
    "SentimentHydrator",
    "ProjectHydrator",
    "RiskTagHydrator",
]
