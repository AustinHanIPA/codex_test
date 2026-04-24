import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from config import MonitorConfig, OnchainConfig, RulesConfig, ThresholdConfig
from models import MarketSnapshot, OnchainEvent, QuantSignal
from rules import RuleEngine


class RuleEngineTests(unittest.TestCase):
    def test_market_rule_triggers_major_alert(self):
        engine = RuleEngine()
        decision = engine.evaluate_market(
            snapshot=MarketSnapshot(pair="BTCUSDT", symbol="BTC", price=65000.0),
            change_percent=4.0,
            thresholds=ThresholdConfig(minor=0.5, moderate=1.5, major=3.0),
            config=MonitorConfig(),
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.level, "major")

    def test_market_rule_filters_low_volume(self):
        engine = RuleEngine()
        config = MonitorConfig(min_volume_24h_usd=100000.0)
        decision = engine.evaluate_market(
            snapshot=MarketSnapshot(
                pair="MEMEUSDT",
                symbol="MEME",
                price=0.01,
                volume_24h=5000.0,
            ),
            change_percent=10.0,
            thresholds=ThresholdConfig(),
            config=config,
        )

        self.assertFalse(decision.should_alert)

    def test_onchain_rule_triggers_whale_alert(self):
        engine = RuleEngine()
        decision = engine.evaluate_onchain(
            OnchainEvent(
                event_id="tx-1",
                source="test",
                event_type="WhaleTransfer",
                amount_usd=100000.0,
            ),
            OnchainConfig(whale_transfer_threshold_usd=50000.0),
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.level, "major")
        self.assertIn("whale-transfer", decision.tags)

    def test_configured_market_rule_records_match(self):
        engine = RuleEngine(
            RulesConfig(
                market=[
                    {
                        "id": "configured-btc-move",
                        "level": "moderate",
                        "tags": ["configured-rule"],
                        "all": [{"symbol_in": ["BTC"]}, {"price_change_abs_gte": 2}],
                    }
                ]
            )
        )
        decision = engine.evaluate_market(
            snapshot=MarketSnapshot(pair="BTCUSDT", symbol="BTC", price=65000.0),
            change_percent=2.2,
            thresholds=ThresholdConfig(),
            config=MonitorConfig(),
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.level, "moderate")
        self.assertEqual(decision.matched_rules, ["configured-btc-move"])

    def test_configured_onchain_rule_records_match(self):
        engine = RuleEngine(
            RulesConfig(
                onchain=[
                    {
                        "id": "new-pair",
                        "level": "moderate",
                        "tags": ["new-pair"],
                        "all": [{"event_type_in": ["NewPairCreated"]}],
                    }
                ]
            )
        )
        decision = engine.evaluate_onchain(
            OnchainEvent(
                event_id="tx-2",
                source="test",
                event_type="NewPairCreated",
                symbol="PEPE",
            ),
            OnchainConfig(),
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.matched_rules, ["new-pair"])

    def test_unknown_configured_condition_does_not_match(self):
        engine = RuleEngine(
            RulesConfig(
                market=[
                    {
                        "id": "typo-rule",
                        "level": "major",
                        "all": [{"price_change_typo": 1}],
                    }
                ]
            )
        )
        decision = engine.evaluate_market(
            snapshot=MarketSnapshot(pair="BTCUSDT", symbol="BTC", price=65000.0),
            change_percent=0.1,
            thresholds=ThresholdConfig(),
            config=MonitorConfig(),
        )

        self.assertFalse(decision.should_alert)

    def test_builtin_quant_signal_triggers_alert(self):
        engine = RuleEngine(RulesConfig(market=[]))
        decision = engine.evaluate_market(
            snapshot=MarketSnapshot(pair="BTCUSDT", symbol="BTC", price=65000.0),
            change_percent=0.1,
            thresholds=ThresholdConfig(),
            config=MonitorConfig(),
            quant_signal=QuantSignal(symbol="BTC", signal="STRONG_BUY", score=82),
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.level, "moderate")
        self.assertEqual(decision.matched_rules, ["builtin-quant-signal"])


if __name__ == "__main__":
    unittest.main()
