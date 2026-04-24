import hashlib
import hmac
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto_monitor"))

from config import get_config
from main import _check_admin, _verify_webhook_signature


class FakeRequest:
    def __init__(self, headers, query=None):
        self.headers = headers
        self.query = query or {}


class WebhookSecurityTests(unittest.TestCase):
    def setUp(self):
        self.config = get_config()
        self.original_secret = self.config.onchain.webhook_signature_secret
        self.original_header = self.config.onchain.webhook_signature_header
        self.original_admin = self.config.service.admin_token

    def tearDown(self):
        self.config.onchain.webhook_signature_secret = self.original_secret
        self.config.onchain.webhook_signature_header = self.original_header
        self.config.service.admin_token = self.original_admin

    def test_signature_disabled_allows_request(self):
        self.config.onchain.webhook_signature_secret = ""
        self.assertTrue(_verify_webhook_signature(FakeRequest({}), b"{}"))

    def test_signature_enabled_validates_hmac(self):
        self.config.onchain.webhook_signature_secret = "secret"
        self.config.onchain.webhook_signature_header = "X-Webhook-Signature"
        timestamp = str(int(time.time()))
        body = b'{"event_id":"tx-1"}'
        signed_payload = f"{timestamp}.".encode("utf-8") + body
        digest = hmac.new(b"secret", signed_payload, hashlib.sha256).hexdigest()

        self.assertTrue(
            _verify_webhook_signature(
                FakeRequest(
                    {
                        "X-Webhook-Timestamp": timestamp,
                        "X-Webhook-Signature": f"sha256={digest}",
                    }
                ),
                body,
            )
        )

    def test_signature_enabled_rejects_bad_hmac(self):
        self.config.onchain.webhook_signature_secret = "secret"
        self.assertFalse(
            _verify_webhook_signature(
                FakeRequest({"X-Webhook-Signature": "sha256=bad"}),
                b"{}",
            )
        )

    def test_admin_token_guards_mutations(self):
        self.config.service.admin_token = "admin-secret"

        self.assertTrue(_check_admin(FakeRequest({"X-Admin-Token": "admin-secret"})))
        self.assertFalse(_check_admin(FakeRequest({"X-Admin-Token": "wrong"})))


if __name__ == "__main__":
    unittest.main()
