"""
Pipeline Orchestrator - 管线编排器。

串联所有阶段：
Query Hydration → Sources → Hydrators → Filters → Scorers → Selector → Side Effects

每阶段支持并发执行和超时控制。
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from logger import get_monitor_logger
from pipeline.base import (
    BaseFilter,
    BaseHydrator,
    BaseScorer,
    BaseSelector,
    BaseSideEffect,
    BaseSource,
)
from pipeline.models import ContentItem, PipelineContext, PipelineResult
from pipeline.query_hydration.query_hydrator import QueryHydrator


class PipelineOrchestrator:
    """
    管线编排器。

    用法：
        orchestrator = PipelineOrchestrator()
        orchestrator.add_source(TwitterSource())
        orchestrator.add_source(MarketSource())
        orchestrator.add_hydrator(PriceHydrator())
        orchestrator.add_filter(DuplicateFilter())
        orchestrator.add_scorer(HotnessScorer())
        orchestrator.set_selector(WeightedSelector())
        orchestrator.add_side_effect(TelegramNotifyEffect())

        result = await orchestrator.run(query="BTC 异动")
    """

    def __init__(
        self,
        query_hydrator: Optional[QueryHydrator] = None,
        source_timeout: float = 30.0,
        hydrator_timeout: float = 20.0,
        stage_timeout: float = 60.0,
    ):
        self.query_hydrator = query_hydrator or QueryHydrator()
        self.source_timeout = source_timeout
        self.hydrator_timeout = hydrator_timeout
        self.stage_timeout = stage_timeout

        self._sources: List[BaseSource] = []
        self._hydrators: List[BaseHydrator] = []
        self._filters: List[BaseFilter] = []
        self._scorers: List[BaseScorer] = []
        self._selector: Optional[BaseSelector] = None
        self._side_effects: List[BaseSideEffect] = []

        self.logger = get_monitor_logger()

    # === 注册组件 ===

    def add_source(self, source: BaseSource) -> "PipelineOrchestrator":
        self._sources.append(source)
        return self

    def add_hydrator(self, hydrator: BaseHydrator) -> "PipelineOrchestrator":
        self._hydrators.append(hydrator)
        return self

    def add_filter(self, filter_: BaseFilter) -> "PipelineOrchestrator":
        self._filters.append(filter_)
        return self

    def add_scorer(self, scorer: BaseScorer) -> "PipelineOrchestrator":
        self._scorers.append(scorer)
        return self

    def set_selector(self, selector: BaseSelector) -> "PipelineOrchestrator":
        self._selector = selector
        return self

    def add_side_effect(self, effect: BaseSideEffect) -> "PipelineOrchestrator":
        self._side_effects.append(effect)
        return self

    # === 执行管线 ===

    async def run(
        self,
        query: str = "",
        user_id: str = "default",
        overrides: Optional[Dict] = None,
    ) -> PipelineResult:
        """执行完整管线。"""
        start_time = time.time()

        # Stage 1: Query Hydration
        self.logger.info("━━━ [Stage 1] Query Hydration ━━━")
        context = await self.query_hydrator.hydrate(
            query=query, user_id=user_id, overrides=overrides
        )

        # Stage 2: Sources - 并发拉取
        self.logger.info("━━━ [Stage 2] Sources ━━━")
        all_items = await self._run_sources(context)
        context.source_counts = self._count_by_source(all_items)
        total_sourced = len(all_items)
        self.logger.info(f"  Sources 产出 {total_sourced} 条内容")

        if not all_items:
            return self._build_result([], context, start_time, total_sourced, 0)

        # Stage 3: Hydrators - 顺序执行（因为可能有依赖）
        self.logger.info("━━━ [Stage 3] Hydrators ━━━")
        all_items = await self._run_hydrators(all_items, context)

        # Stage 4: Filters - 顺序执行
        self.logger.info("━━━ [Stage 4] Filters ━━━")
        all_items = await self._run_filters(all_items, context)
        total_after_filter = len([it for it in all_items if not it.filtered])
        self.logger.info(f"  Filters 后剩余 {total_after_filter} 条")

        # Stage 5: Scorers - 并发打分
        self.logger.info("━━━ [Stage 5] Scorers ━━━")
        all_items = await self._run_scorers(all_items, context)

        # Stage 6: Selector/Blender
        self.logger.info("━━━ [Stage 6] Selector ━━━")
        selected_items = await self._run_selector(all_items, context)
        self.logger.info(f"  Selector 选出 {len(selected_items)} 条")

        # Stage 7: Side Effects - 并发执行
        self.logger.info("━━━ [Stage 7] Side Effects ━━━")
        await self._run_side_effects(selected_items, context)

        return self._build_result(
            selected_items, context, start_time, total_sourced, total_after_filter
        )

    # === 内部执行方法 ===

    async def _run_sources(self, context: PipelineContext) -> List[ContentItem]:
        """并发执行所有 Source。"""
        if not self._sources:
            self.logger.warning("无注册数据源")
            return []

        tasks = [
            self._run_single_source(source, context) for source in self._sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: List[ContentItem] = []
        for source, result in zip(self._sources, results):
            if isinstance(result, Exception):
                self.logger.error(f"  Source [{source.source_name}] 异常: {result}")
            elif isinstance(result, list):
                all_items.extend(result)
                self.logger.info(f"  Source [{source.source_name}] 产出 {len(result)} 条")
            else:
                self.logger.warning(f"  Source [{source.source_name}] 返回非法类型")

        return all_items

    async def _run_single_source(
        self, source: BaseSource, context: PipelineContext
    ) -> List[ContentItem]:
        """单个 Source 的超时包装执行。"""
        try:
            return await asyncio.wait_for(
                source.fetch(context), timeout=self.source_timeout
            )
        except asyncio.TimeoutError:
            self.logger.error(f"  Source [{source.source_name}] 超时 ({self.source_timeout}s)")
            return []

    async def _run_hydrators(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """顺序执行所有 Hydrator。"""
        for hydrator in self._hydrators:
            stage_start = time.time()
            try:
                items = await asyncio.wait_for(
                    hydrator.hydrate(items, context),
                    timeout=self.hydrator_timeout,
                )
                elapsed = time.time() - stage_start
                context.stage_timings[f"hydrator_{hydrator.hydrator_name}"] = elapsed
                self.logger.info(f"  Hydrator [{hydrator.hydrator_name}] 完成 ({elapsed:.2f}s)")
            except asyncio.TimeoutError:
                self.logger.error(
                    f"  Hydrator [{hydrator.hydrator_name}] 超时 ({self.hydrator_timeout}s)"
                )
            except Exception as exc:
                self.logger.error(f"  Hydrator [{hydrator.hydrator_name}] 异常: {exc}")

        return items

    async def _run_filters(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """顺序执行所有 Filter。"""
        for filter_ in self._filters:
            stage_start = time.time()
            before_count = len([it for it in items if not it.filtered])
            try:
                items = await asyncio.wait_for(
                    filter_.apply(items, context),
                    timeout=self.stage_timeout,
                )
                after_count = len([it for it in items if not it.filtered])
                filtered_count = before_count - after_count
                context.filter_stats[filter_.filter_name] = filtered_count

                elapsed = time.time() - stage_start
                context.stage_timings[f"filter_{filter_.filter_name}"] = elapsed
                self.logger.info(
                    f"  Filter [{filter_.filter_name}] 过滤 {filtered_count} 条 ({elapsed:.2f}s)"
                )
            except asyncio.TimeoutError:
                self.logger.error(
                    f"  Filter [{filter_.filter_name}] 超时"
                )
            except Exception as exc:
                self.logger.error(f"  Filter [{filter_.filter_name}] 异常: {exc}")

        return items

    async def _run_scorers(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """并发执行所有 Scorer（各 Scorer 独立打分互不依赖）。"""
        if not self._scorers:
            return items

        tasks = [scorer.score(items, context) for scorer in self._scorers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for scorer, result in zip(self._scorers, results):
            if isinstance(result, Exception):
                self.logger.error(f"  Scorer [{scorer.scorer_name}] 异常: {result}")
            else:
                self.logger.info(f"  Scorer [{scorer.scorer_name}] 完成")

        return items

    async def _run_selector(
        self, items: List[ContentItem], context: PipelineContext
    ) -> List[ContentItem]:
        """执行 Selector。"""
        if self._selector is None:
            # 无 Selector 时按 score_final 简单排序
            active = [it for it in items if not it.filtered]
            active.sort(key=lambda x: x.score_final, reverse=True)
            return active[: context.max_items]

        try:
            return await asyncio.wait_for(
                self._selector.select(items, context),
                timeout=self.stage_timeout,
            )
        except asyncio.TimeoutError:
            self.logger.error("Selector 超时，降级为简单排序")
            active = [it for it in items if not it.filtered]
            active.sort(key=lambda x: x.score_final, reverse=True)
            return active[: context.max_items]

    async def _run_side_effects(
        self, items: List[ContentItem], context: PipelineContext
    ) -> None:
        """并发执行所有 Side Effects。"""
        if not self._side_effects:
            return

        tasks = [effect.execute(items, context) for effect in self._side_effects]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for effect, result in zip(self._side_effects, results):
            if isinstance(result, Exception):
                self.logger.error(f"  SideEffect [{effect.effect_name}] 异常: {result}")
            else:
                self.logger.info(f"  SideEffect [{effect.effect_name}] 完成")

    # === 辅助方法 ===

    @staticmethod
    def _count_by_source(items: List[ContentItem]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            counts[item.source] = counts.get(item.source, 0) + 1
        return counts

    @staticmethod
    def _build_result(
        items: List[ContentItem],
        context: PipelineContext,
        start_time: float,
        total_sourced: int,
        total_after_filter: int,
    ) -> PipelineResult:
        elapsed_ms = (time.time() - start_time) * 1000
        return PipelineResult(
            items=items,
            context=context,
            total_sourced=total_sourced,
            total_after_filter=total_after_filter,
            total_selected=len(items),
            duration_ms=elapsed_ms,
        )
