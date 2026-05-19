"""
Filters 层 - 过滤不合格内容。

- DuplicateFilter: 去重
- ScamFilter: 诈骗币过滤
- StaleFilter: 旧闻过滤
- LowCredibilityFilter: 低可信来源过滤
"""
from pipeline.filters.duplicate_filter import DuplicateFilter
from pipeline.filters.scam_filter import ScamFilter
from pipeline.filters.stale_filter import StaleFilter
from pipeline.filters.low_credibility_filter import LowCredibilityFilter

__all__ = [
    "DuplicateFilter",
    "ScamFilter",
    "StaleFilter",
    "LowCredibilityFilter",
]
