"""
Sources 层 - 从各种渠道拉取原始内容。

支持的数据源:
- Twitter/X 热点
- YouTube 视频
- Reddit 帖子
- 新闻聚合
- 链上数据
- KOL 发言
"""
from pipeline.sources.twitter_source import TwitterSource
from pipeline.sources.youtube_source import YouTubeSource
from pipeline.sources.reddit_source import RedditSource
from pipeline.sources.news_source import NewsSource
from pipeline.sources.onchain_source import OnchainSource
from pipeline.sources.kol_source import KOLSource
from pipeline.sources.market_source import MarketSource

__all__ = [
    "TwitterSource",
    "YouTubeSource",
    "RedditSource",
    "NewsSource",
    "OnchainSource",
    "KOLSource",
    "MarketSource",
]
