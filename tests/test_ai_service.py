import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from ai_service import AIService


class AIServiceParseTests(unittest.TestCase):
    def test_parse_json_payload(self):
        service = AIService()
        insight = service._parse_insight(
            '{"comment":"🚀 多头情绪升温","sentiment":"bullish",'
            '"event_type":"price_movement","risk_hint":"注意追高风险",'
            '"suggested_action":"等待回踩","confidence":0.82}'
        )

        self.assertEqual(insight.comment, "🚀 多头情绪升温")
        self.assertEqual(insight.sentiment, "bullish")
        self.assertEqual(insight.event_type, "price_movement")
        self.assertEqual(insight.risk_hint, "注意追高风险")
        self.assertEqual(insight.suggested_action, "等待回踩")
        self.assertEqual(insight.confidence, 0.82)

    def test_parse_plain_text_fallback(self):
        service = AIService()
        insight = service._parse_insight("📉 跌幅扩大，别急着抄底，先看量能。")

        self.assertEqual(insight.comment, "📉 跌幅扩大，别急着抄底，先看量能。")
        self.assertEqual(insight.sentiment, "neutral")


if __name__ == "__main__":
    unittest.main()
