"""
规则引擎。

当前实现先覆盖两类场景：
1. 价格监控的组合条件过滤
2. 链上巨鲸事件触发
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from config import MonitorConfig, OnchainConfig, ThresholdConfig
from models import MarketSnapshot, OnchainEvent


@dataclass
class RuleDecision:
    should_alert: bool
    level: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class RuleEngine:
    """组合条件规则引擎。"""

    def evaluate_market(
        self,
        snapshot: MarketSnapshot,
        change_percent: float,
        thresholds: ThresholdConfig,
        config: MonitorConfig,
    ) -> RuleDecision:
        abs_change = abs(change_percent)
        reasons: List[str] = []
        level: Optional[str] = None

        if abs_change >= thresholds.major:
            level = "major"
        elif abs_change >= thresholds.moderate:
            level = "moderate"
        elif abs_change >= thresholds.minor:
            level = "minor"

        if level is None:
            return RuleDecision(should_alert=False, reasons=["price threshold not met"])

        reasons.append(f"price change {change_percent:+.2f}% >= {level} threshold")

        if config.min_market_cap_usd > 0 and snapshot.market_cap is not None:
            if snapshot.market_cap < config.min_market_cap_usd:
                return RuleDecision(
                    should_alert=False,
                    level=level,
                    reasons=reasons + [f"market cap {snapshot.market_cap:.2f} < required floor"],
                )
            reasons.append("market cap rule satisfied")

        if config.min_volume_24h_usd > 0 and snapshot.volume_24h is not None:
            if snapshot.volume_24h < config.min_volume_24h_usd:
                return RuleDecision(
                    should_alert=False,
                    level=level,
                    reasons=reasons + [f"24h volume {snapshot.volume_24h:.2f} < required floor"],
                )
            reasons.append("24h volume rule satisfied")

        tags = []
        if snapshot.market_cap and snapshot.market_cap < 1_000_000:
            tags.append("small-cap")
        if snapshot.liquidity_usd and snapshot.liquidity_usd < 50_000:
            tags.append("low-liquidity")

        return RuleDecision(should_alert=True, level=level, reasons=reasons, tags=tags)

    def evaluate_onchain(self, event: OnchainEvent, config: OnchainConfig) -> RuleDecision:
        if not config.enabled:
            return RuleDecision(should_alert=False, reasons=["onchain monitoring disabled"])

        tracked = {address.lower() for address in config.tracked_addresses}
        event_addresses = {value.lower() for value in [event.address, event.counterparty] if value}

        if tracked and not (tracked & event_addresses):
            return RuleDecision(should_alert=False, reasons=["event not related to tracked addresses"])

        threshold = config.whale_transfer_threshold_usd
        if event.amount_usd is not None and event.amount_usd >= threshold:
            return RuleDecision(
                should_alert=True,
                level="major",
                reasons=[f"whale transfer >= {threshold:.2f} USD"],
                tags=["whale-transfer"],
            )

        if tracked and event_addresses:
            return RuleDecision(
                should_alert=True,
                level="moderate",
                reasons=["tracked address activity detected"],
                tags=["tracked-address"],
            )

        return RuleDecision(should_alert=False, reasons=["onchain threshold not met"])
