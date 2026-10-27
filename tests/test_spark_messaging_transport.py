"""Exercise provider failures through the real HTTP response adapter."""
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from spark_messaging_hub import default_transport, HubError, MessagingHub
from spark_credential_store import CredentialStore
from spark_telegram import TelegramBotAPI, TelegramError


class MessagingTransportTests(unittest.TestCase):
    def test_provider_http_errors_retain_telegram_failure_classification(self):
        token = "123:test-secret"
        for code, kind, extra in (
            (401, "auth", {}),
            (403, "auth", {}),
            (409, "conflict", {}),
            (429, "rate_limited", {"parameters": {"retry_after": 37}}),
        ):
            with self.subTest(code=code):
                payload = json.dumps({"ok": False, "error_code": code, **extra}).encode()
                error = HTTPError("https://api.telegram.org/bot" + token + "/getMe",
                                  code, "provider failure", {}, io.BytesIO(payload))
                with patch("spark_messaging_hub.urlrequest.urlopen", side_effect=error):
                    with self.assertRaises(TelegramError) as caught:
                        TelegramBotAPI(token).get_me()
                self.assertEqual(caught.exception.kind, kind)
                self.assertEqual(caught.exception.error_code, code)
                self.assertNotIn(token, str(caught.exception))
                if code == 429:
                    self.assertEqual(caught.exception.retry_after, 37)

    def test_connection_failure_remains_a_network_error(self):
        with patch("spark_messaging_hub.urlrequest.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(TelegramError) as caught:
                TelegramBotAPI("123:test-secret").get_me()
        self.assertEqual(caught.exception.kind, "network")

    def test_successful_response_is_preserved(self):
        response = io.BytesIO(b'{"ok": true}')
        response.status = 200
        with patch("spark_messaging_hub.urlrequest.urlopen", return_value=response):
            self.assertEqual(default_transport("GET", "https://example.test"),
                             (200, '{"ok": true}'))

    def test_discord_secret_survives_reopen_without_plaintext_in_database(self):
        webhook = "https://discord.com/api/webhooks/123/test-secret"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CredentialStore(root / "credentials",
                                    protector=lambda value: value[::-1],
                                    unprotector=lambda value: value[::-1])
            configured = MessagingHub(root, secret_store=store).configure("discord", {
                "webhook_url": webhook, "allowed_channel_id": "456"})
            self.assertEqual(configured["credential_store"], "dpapi")
            self.assertNotIn(b"test-secret", (root / "messaging-hub/messages.sqlite3").read_bytes())
            hub = MessagingHub(root, secret_store=store)
            approval = hub.approve_outbound("discord", "456", "Approved test")
            with patch("spark_messaging_hub.default_transport", return_value=(204, "")) as transport:
                self.assertEqual(hub.send("discord", approval["approval_id"])["state"], "sent")
            self.assertEqual(transport.call_args.args[1], webhook)
            store.delete("discord_webhook_url")
            with self.assertRaisesRegex(HubError, "credential is missing"):
                hub._config("discord")
