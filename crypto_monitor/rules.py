"""
规则引擎。

当前实现先覆盖两类场景：
1. 价格监控的组合条件过滤
2. 链上巨鲸事件触发
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from config import MonitorConfig, OnchainConfig, RulesConfig, ThresholdConfig
from models import MarketSnapshot, OnchainEvent


@dataclass
class RuleDecision:
    should_alert: bool
    level: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)


class RuleEngine:
    """组合条件规则引擎。"""

    def __init__(self, rules_config: Optional[RulesConfig] = None):
        self.rules_config = rules_config or RulesConfig()

    def evaluate_market(
        self,
        snapshot: MarketSnapshot,
        change_percent: float,
        thresholds: ThresholdConfig,
        config: MonitorConfig,
    ) -> RuleDecision:
        reasons: List[str] = []

        if config.min_market_cap_usd > 0 and snapshot.market_cap is not None:
            if snapshot.market_cap < config.min_market_cap_usd:
                return RuleDecision(
                    should_alert=False,
                    reasons=[f"market cap {snapshot.market_cap:.2f} < required floor"],
                )
            reasons.append("market cap rule satisfied")

        if config.min_volume_24h_usd > 0 and snapshot.volume_24h is not None:
            if snapshot.volume_24h < config.min_volume_24h_usd:
                return RuleDecision(
                    should_alert=False,
                    reasons=[f"24h volume {snapshot.volume_24h:.2f} < required floor"],
                )
            reasons.append("24h volume rule satisfied")

        configured = self._evaluate_market_rules(snapshot, change_percent)
        if configured is not None:
            configured.reasons = reasons + configured.reasons
            return configured

        abs_change = abs(change_percent)
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

        tags = []
        if snapshot.market_cap and snapshot.market_cap < 1_000_000:
            tags.append("small-cap")
        if snapshot.liquidity_usd and snapshot.liquidity_usd < 50_000:
            tags.append("low-liquidity")

        return RuleDecision(should_alert=True, level=level, reasons=reasons, tags=tags)

    def evaluate_onchain(self, event: OnchainEvent, config: OnchainConfig) -> RuleDecision:
        if not config.enabled:
            return RuleDecision(should_alert=False, reasons=["onchain monitoring disabled"])

        configured = self._evaluate_onchain_rules(event)
        if configured is not None:
            return configured

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

    def _evaluate_market_rules(
        self,
        snapshot: MarketSnapshot,
        change_percent: float,
    ) -> Optional[RuleDecision]:
        if not self.rules_config.enabled or not self.rules_config.market:
            return None

        matches = []
        for rule in self.rules_config.market:
            if not self._is_rule_enabled(rule):
                continue
            conditions = self._rule_conditions(rule)
            if conditions and self._all_market_conditions(conditions, snapshot, change_percent):
                matches.append(rule)

        if not matches:
            return None
        return self._build_configured_decision(matches, "configured market rule matched")

    def _evaluate_onchain_rules(self, event: OnchainEvent) -> Optional[RuleDecision]:
        if not self.rules_config.enabled or not self.rules_config.onchain:
            return None

        matches = []
        for rule in self.rules_config.onchain:
            if not self._is_rule_enabled(rule):
                continue
            conditions = self._rule_conditions(rule)
            if conditions and self._all_onchain_conditions(conditions, event):
                matches.append(rule)

        if not matches:
            return None
        return self._build_configured_decision(matches, "configured onchain rule matched")

    @staticmethod
    def _is_rule_enabled(rule: Dict[str, Any]) -> bool:
        return bool(rule.get("enabled", True))

    @staticmethod
    def _rule_conditions(rule: Dict[str, Any]) -> List[Dict[str, Any]]:
        conditions = rule.get("all") or rule.get("conditions") or []
        return [item for item in conditions if isinstance(item, dict)]

    def _build_configured_decision(self, matches: List[Dict[str, Any]], reason: str) -> RuleDecision:
        level = self._highest_level([str(rule.get("level") or "minor") for rule in matches])
        matched_rules = [str(rule.get("id") or "anonymous-rule") for rule in matches]
        tags = []
        for rule in matches:
            tags.extend(str(item) for item in rule.get("tags", []))
        return RuleDecision(
            should_alert=True,
            level=level,
            reasons=[f"{reason}: {rule_id}" for rule_id in matched_rules],
            tags=sorted(set(tags)),
            matched_rules=matched_rules,
        )

    @staticmethod
    def _highest_level(levels: Iterable[str]) -> str:
        priority = {"minor": 1, "moderate": 2, "major": 3}
        return max(levels, key=lambda item: priority.get(item, 0), default="minor")

    def _all_market_conditions(
        self,
        conditions: List[Dict[str, Any]],
        snapshot: MarketSnapshot,
        change_percent: float,
    ) -> bool:
        return all(self._match_market_condition(condition, snapshot, change_percent) for condition in conditions)

    def _match_market_condition(
        self,
        condition: Dict[str, Any],
        snapshot: MarketSnapshot,
        change_percent: float,
    ) -> bool:
        for key, expected in condition.items():
            if key == "price_change_abs_gte":
                if abs(change_percent) < float(expected):
                    return False
            elif key == "price_change_gte":
                if change_percent < float(expected):
                    return False
            elif key == "price_change_lte":
                if change_percent > float(expected):
                    return False
            elif key == "market_cap_gte":
                if not self._gte(snapshot.market_cap, expected):
                    return False
            elif key == "volume_24h_gte":
                if not self._gte(snapshot.volume_24h, expected):
                    return False
            elif key == "liquidity_gte":
                if not self._gte(snapshot.liquidity_usd, expected):
                    return False
            elif key == "symbol_in":
                if snapshot.symbol.upper() not in self._upper_set(expected):
                    return False
            else:
                return False
        return True

    def _all_onchain_conditions(self, conditions: List[Dict[str, Any]], event: OnchainEvent) -> bool:
        return all(self._match_onchain_condition(condition, event) for condition in conditions)

    def _match_onchain_condition(self, condition: Dict[str, Any], event: OnchainEvent) -> bool:
        for key, expected in condition.items():
            if key == "amount_usd_gte":
                if not self._gte(event.amount_usd, expected):
                    return False
            elif key == "amount_gte":
                if not self._gte(event.amount, expected):
                    return False
            elif key == "event_type_in":
                if event.event_type not in {str(item) for item in self._list(expected)}:
                    return False
            elif key == "symbol_in":
                if event.symbol.upper() not in self._upper_set(expected):
                    return False
            elif key == "source_in":
                if event.source.lower() not in {str(item).lower() for item in self._list(expected)}:
                    return False
            elif key == "direction_eq":
                if event.direction.lower() != str(expected).lower():
                    return False
            elif key == "address_in":
                allowed = {str(item).lower() for item in self._list(expected)}
                addresses = {value.lower() for value in [event.address, event.counterparty] if value}
                if not (addresses & allowed):
                    return False
            else:
                return False
        return True

    @staticmethod
    def _gte(actual: Optional[float], expected: Any) -> bool:
        if actual is None:
            return False
        try:
            return actual >= float(expected)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        return [value]

    def _upper_set(self, value: Any) -> set[str]:
        return {str(item).upper() for item in self._list(value)}
