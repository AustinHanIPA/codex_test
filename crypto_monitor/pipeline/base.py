"""
Pipeline 各层的抽象基类。

每一层都遵循统一的接口约定，方便扩展和测试。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from pipeline.models import ContentItem, PipelineContext


class BaseSource(ABC):
    """数据源基类 - 负责从外部获取原始内容。"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源名称。"""
        ...

    @abstractmethod
    async def fetch(self, context: PipelineContext) -> List[ContentItem]:
        """从数据源拉取内容列表。"""
        ...


class BaseHydrator(ABC):
    """Hydrator 基类 - 负责为内容项补充元数据。"""

    @property
    @abstractmethod
    def hydrator_name(self) -> str:
        """Hydrator 名称。"""
        ...

    @abstractmethod
    async def hydrate(self, items: List[ContentItem], context: PipelineContext) -> List[ContentItem]:
        """为内容项补充元数据，返回增强后的列表。"""
        ...


class BaseFilter(ABC):
    """Filter 基类 - 负责过滤不合格的内容。"""

    @property
    @abstractmethod
    def filter_name(self) -> str:
        """Filter 名称。"""
        ...

    @abstractmethod
    async def apply(self, items: List[ContentItem], context: PipelineContext) -> List[ContentItem]:
        """过滤内容，返回通过过滤的列表（被过滤的标记 filtered=True）。"""
        ...


class BaseScorer(ABC):
    """Scorer 基类 - 负责为内容打分。"""

    @property
    @abstractmethod
    def scorer_name(self) -> str:
        """Scorer 名称。"""
        ...

    @abstractmethod
    async def score(self, items: List[ContentItem], context: PipelineContext) -> List[ContentItem]:
        """为内容打分，返回带评分的列表。"""
        ...


class BaseSelector(ABC):
    """Selector/Blender 基类 - 负责混排和选取最终推荐集。"""

    @abstractmethod
    async def select(self, items: List[ContentItem], context: PipelineContext) -> List[ContentItem]:
        """从候选集中选出最终推荐列表。"""
        ...


class BaseSideEffect(ABC):
    """Side Effect 基类 - 负责管线执行后的副作用操作。"""

    @property
    @abstractmethod
    def effect_name(self) -> str:
        """副作用名称。"""
        ...

    @abstractmethod
    async def execute(self, items: List[ContentItem], context: PipelineContext) -> None:
        """执行副作用（记录、反馈、更新）。"""
        ...
