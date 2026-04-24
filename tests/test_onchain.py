import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from onchain import normalize_onchain_payload


class OnchainAdapterTests(unittest.TestCase):
    def test_normalizes_helius_token_transfer(self):
        events = normalize_onchain_payload(
            [
                {
                    "signature": "sig-1",
                    "type": "TRANSFER",
                    "tokenTransfers": [
                        {
                            "fromUserAccount": "wallet-a",
                            "toUserAccount": "wallet-b",
                            "tokenAmount": 1200,
                            "mint": "SOL",
                        }
                    ],
                    "amountUsd": 75000,
                    "timestamp": "2026-04-24T08:00:00",
                }
            ],
            source="helius",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "sig-1")
        self.assertEqual(events[0].event_type, "WhaleTransfer")
        self.assertEqual(events[0].address, "wallet-a")
        self.assertEqual(events[0].counterparty, "wallet-b")
        self.assertEqual(events[0].symbol, "SOL")
        self.assertEqual(events[0].amount_usd, 75000.0)

    def test_normalizes_wrapped_quicknode_payload(self):
        events = normalize_onchain_payload(
            {
                "data": [
                    {
                        "transactionHash": "0xabc",
                        "eventType": "PAIR_CREATED",
                        "asset": "PEPE",
                        "valueUsd": "120000",
                    }
                ]
            },
            source="quicknode",
        )

        self.assertEqual(events[0].event_type, "NewPairCreated")
        self.assertEqual(events[0].symbol, "PEPE")
        self.assertEqual(events[0].amount_usd, 120000.0)


if __name__ == "__main__":
    unittest.main()
