"""Capabilities 02 & 06 — Messaging hub and WhatsApp offline acceptance.

All transport calls are faked with API-shaped real payloads (no network,
accounts or real sends). Live account/channel acceptance requires actual
tokens on the founder's machine and is documented, never claimed here.
"""
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import spark_messaging_hub as hub_module
from spark_messaging_hub import (HubError, MessagingHub, PROVIDERS,
                                 register_provider)


class FakeTransport:
    """Deterministic HTTP stand-in that records every outgoing request."""

    def __init__(self, script=None):
        self.script = script or {}
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=15):
        self.calls.append({"method": method, "url": url,
                           "headers": headers or {}, "body": body})
        for pattern, response in self.script.items():
            if pattern in url:
                if callable(response):
                    return response()
                status, text = response
                return status, text
        return 500, '{"error":"unrouted test call"}'


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(_temp()))
        self.now = time.time()
        self.transport = FakeTransport()
        original = hub_module.default_transport
        hub_module.default_transport = self.transport
        self.addCleanup(setattr, hub_module, "default_transport", original)
        self.hub = MessagingHub(self.dir, clock=lambda: self.now)

    def approve(self, channel, recipient, text):
        return self.hub.approve_outbound(channel, recipient, text)


def _temp():
    import tempfile
    return tempfile.TemporaryDirectory()


class PolicyTests(unittest.TestCase):
    def test_nothing_enabled_by_default_and_no_open_relay(self):
        with _temp() as d:
            hub = MessagingHub(Path(d))
            status = hub.status()
            self.assertEqual(status["channels"], {})
            self.assertIn("no open relay", status["policy"])
            self.assertNotIn("open", status["channels"])

    def test_provider_catalog_has_seven_channels_exact(self):
        self.assertEqual(set(PROVIDERS),
                         {"telegram", "whatsapp", "whatsapp_bridge",
                          "slack", "discord", "teams", "signal"})

    def test_extensible_registration_is_guarded(self):
        from spark_messaging_hub import Provider

        class WebChat(Provider):
            name = "webchat"

        register_provider("webchat", WebChat)
        self.addCleanup(PROVIDERS.pop, "webchat", None)
        self.assertIn("webchat", PROVIDERS)
        with self.assertRaises(HubError):
            register_provider("Invalid Name!", WebChat)

        class NotAProvider:
            pass

        with self.assertRaises(HubError):
            register_provider("broken", NotAProvider)


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(self.enterContext(_temp()))
        self.hub = MessagingHub(self.dir)

    def test_unknown_provider_rejected(self):
        with self.assertRaises(HubError):
            self.hub.configure("carrier-pigeon", {})

    def test_configuration_is_validated_and_persisted(self):
        result = self.hub.configure("telegram", {"bot_token": " 123:abc ", "allowed_chat_id": "42"})
        self.assertTrue(result["configured"])
        status = self.hub.status()
        self.assertEqual(status["channels"]["telegram"]["state"], "configured, untested")
        self.assertTrue(status["channels"]["telegram"]["inbound_polling"])
        with self.assertRaises(HubError):
            self.hub.configure("telegram", {"bad key!": "x"})
        with self.assertRaises(HubError):
            self.hub.configure({"telegram", "long"}, {})

    def test_disconnect_revokes_and_status_reports_absent(self):
        self.hub.configure("slack", {"bot_token": "xoxb-1", "allowed_channel": "C1"})
        revoked = self.hub.disconnect("slack")
        self.assertFalse(revoked["configured"])
        self.assertNotIn("slack", self.hub.status()["channels"])
        with self.assertRaises(HubError):
            self.hub.disconnect("not-a-channel")


class SecureTelegramConfigTests(unittest.TestCase):
    class Store:
        def __init__(self):
            self.token = None
        def save_telegram_token(self, token):
            self.token = token
        def load_telegram_token(self):
            return self.token

    def test_token_is_never_persisted_in_sqlite(self):
        with _temp() as d:
            store = self.Store()
            hub = MessagingHub(Path(d), secret_store=store)
            result = hub.configure("telegram", {"bot_token": "123:secret-token",
                                                "allowed_chat_id": "42"})
            self.assertEqual(result["credential_store"], "dpapi")
            self.assertEqual(store.token, "123:secret-token")
            db = Path(d) / "messaging-hub" / "messages.sqlite3"
            raw = db.read_bytes()
            self.assertNotIn(b"123:secret-token", raw)
            self.assertIn(hub_module.TELEGRAM_TOKEN_SENTINEL.encode(), raw)

    def test_unenrolled_marker_fails_closed(self):
        with _temp() as d:
            store = self.Store()
            hub = MessagingHub(Path(d), secret_store=store)
            hub.configure("telegram", {"bot_token": hub_module.TELEGRAM_TOKEN_SENTINEL,
                                       "allowed_chat_id": "42"})
            with self.assertRaises(HubError):
                hub.receive("telegram")

    def test_status_migrates_legacy_plaintext_token_into_dpapi(self):
        with _temp() as d:
            store = self.Store()
            hub = MessagingHub(Path(d), secret_store=store)
            legacy = {"__kind": "telegram", "bot_token": "999:legacy-token",
                      "allowed_chat_id": "42"}
            with hub._db() as db:
                db.execute("INSERT INTO provider_config VALUES(?,?,?)",
                           ("telegram", json.dumps(legacy), 1.0))
            status = hub.status()
            self.assertIn("telegram", status["channels"])
            self.assertEqual(store.token, "999:legacy-token")
            raw = (Path(d) / "messaging-hub" / "messages.sqlite3").read_bytes()
            self.assertNotIn(b"999:legacy-token", raw)
            self.assertIn(hub_module.TELEGRAM_TOKEN_SENTINEL.encode(), raw)


class OutboundFlowTests(Base):
    def test_send_requires_prior_exact_approval(self):
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        with self.assertRaises(HubError):
            self.hub.send("telegram", "apr-fake")

    def test_sender_uses_allowlisted_transport_and_records_message_id(self):
        self.transport.script["sendMessage"] = (200, json.dumps(
            {"ok": True, "result": {"message_id": 777}}))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42,43"})
        approval = self.approve("telegram", "42", "Daily report ready")
        result = self.hub.send("telegram", approval["approval_id"])
        self.assertEqual(result["state"], "sent")
        self.assertEqual(result["message_id"], "777")
        self.assertIn("sendMessage", self.transport.calls[0]["url"])
        sent = json.loads(self.transport.calls[0]["body"])
        self.assertEqual(sent["text"], "Daily report ready")
        history = self.hub.history()
        self.assertEqual(history["messages"][0]["state"], "sent")

    def test_allowlisted_recipient_only(self):
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        approval = self.approve("telegram", "999", "No")
        with self.assertRaises(HubError):
            self.hub.send("telegram", approval["approval_id"])
        failed = self.hub.history()
        self.assertEqual(failed["messages"][0]["state"], "failed")

    def test_approval_is_single_use(self):
        self.transport.script["sendMessage"] = (200, json.dumps(
            {"ok": True, "result": {"message_id": 1}}))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        approval = self.approve("telegram", "42", "Once only")
        self.hub.send("telegram", approval["approval_id"])
        replayed = self.hub.approve_outbound("telegram", "42", "Once only")
        self.assertNotEqual(replayed["approval_id"], approval["approval_id"])

    def test_approval_expiry_blocks_send(self):
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        approval = self.approve("telegram", "42", "Later")
        self.now += 700
        with self.assertRaises(HubError):
            self.hub.send("telegram", approval["approval_id"])

    def test_transport_failure_is_audited_and_state_stays_failed(self):
        self.transport.script["sendMessage"] = (401, json.dumps({"ok": False, "description": "Unauthorized"}))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        approval = self.approve("telegram", "42", "Blocked by auth")
        with self.assertRaises(HubError):
            self.hub.send("telegram", approval["approval_id"])
        entry = self.hub.history()["messages"][0]
        self.assertEqual(entry["state"], "failed")
        self.assertIn("Unauthorized", entry["error"])
        status = self.hub.status()
        self.assertEqual(status["channels"]["telegram"]["state"], "failed")

    def test_rate_limit_blocks_the_fifty_first_send(self):
        self.transport.script["sendMessage"] = (200, json.dumps(
            {"ok": True, "result": {"message_id": 5}}))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        for index in range(50):
            approval = self.approve("telegram", "42", f"Message {index}")
            self.hub.send("telegram", approval["approval_id"])
            self.now += 1
        approval = self.approve("telegram", "42", "One too many")
        with self.assertRaises(HubError) as caught:
            self.hub.send("telegram", approval["approval_id"])
        self.assertIn("rate limit", str(caught.exception))


class WhatsAppTests(Base):
    CLOUD_CONFIG = {"access_token": "EAAG...", "phone_number_id": "12345",
                    "allowed_recipient": "911234567890",
                    "understood_pricing": True}

    def test_cloud_send_without_pricing_consent_is_refused(self):
        config = dict(self.CLOUD_CONFIG, understood_pricing=False)
        self.hub.configure("whatsapp", config)
        approval = self.approve("whatsapp", "911234567890", "Check the report")
        with self.assertRaises(HubError) as caught:
            self.hub.send("whatsapp", approval["approval_id"])
        self.assertIn("pricing", str(caught.exception))
        self.assertEqual(self.transport.calls, [])

    def test_cloud_send_success_shape_is_real_metadata_format(self):
        self.transport.script["graph.facebook.com/v21.0"] = (200, json.dumps(
            {"messaging_product": "whatsapp",
             "contacts": [{"input": "911234567890", "wa_id": "911234567890"}],
             "messages": [{"id": "wamid.HBgLMTY0MDM1NTAwNTUFVAgA"}]}))
        self.hub.configure("whatsapp", self.CLOUD_CONFIG)
        approval = self.approve("whatsapp", "911234567890", "Verified read, no claims")
        result = self.hub.send("whatsapp", approval["approval_id"])
        self.assertEqual(result["state"], "sent")
        self.assertEqual(result["message_id"], "wamid.HBgLMTY0MDM1NTAwNTUFVAgA")
        sent = json.loads(self.transport.calls[0]["body"])
        self.assertEqual(sent["messaging_product"], "whatsapp")
        self.assertEqual(sent["to"], "911234567890")
        self.assertIn("Bearer", self.transport.calls[0]["headers"]["Authorization"])

    def test_cloud_auth_failure_reports_401_not_a_fabricated_delivery(self):
        self.transport.script["graph.facebook.com"] = (401, json.dumps(
            {"error": {"message": "Invalid OAuth access token",
                       "type": "OAuthException", "code": 2500}}))
        self.hub.configure("whatsapp", self.CLOUD_CONFIG)
        approval = self.approve("whatsapp", "911234567890", "Describe the leak")
        with self.assertRaises(HubError) as caught:
            self.hub.send("whatsapp", approval["approval_id"])
        self.assertIn("401", str(caught.exception))
        entry = self.hub.history()["messages"][0]
        self.assertEqual(entry["state"], "failed")

    def test_cloud_inbound_is_not_fabricated(self):
        self.hub.configure("whatsapp", self.CLOUD_CONFIG)
        with self.assertRaises(HubError) as caught:
            self.hub.receive("whatsapp")
        self.assertIn("webhook", str(caught.exception))

    def test_bridge_requires_explicit_informed_opt_in(self):
        self.hub.configure("whatsapp_bridge", {"bridge_url": "http://127.0.0.1:8777",
                                               "allowed_recipient": "911234567890"})
        approval = self.approve("whatsapp_bridge", "911234567890", "Risky send")
        with self.assertRaises(HubError) as caught:
            self.hub.send("whatsapp_bridge", approval["approval_id"])
        self.assertIn("opt-in", str(caught.exception))
        self.assertEqual(self.transport.calls, [])

    def test_bridge_send_with_informed_opt_in_records_transparency(self):
        self.transport.script["/send/text"] = (200, "sent:true")
        self.hub.configure("whatsapp_bridge", {"bridge_url": "http://127.0.0.1:8777",
                                               "allowed_recipient": "911234567890",
                                               "understood_risks": True})
        approval = self.approve("whatsapp_bridge", "911234567890", "Opted-in send")
        result = self.hub.send("whatsapp_bridge", approval["approval_id"])
        self.assertEqual(result["transport"], "bridge")
        self.assertEqual(result["state"], "sent")


class InboundFlowTests(Base):
    TELEGRAM_UPDATES = {
        "ok": True,
        "result": [
            {"update_id": 8001, "message": {"chat": {"id": 42}, "text": "Summarize the digest"}},
            {"update_id": 8002, "message": {"chat": {"id": 777}, "text": "Stranger"}},
        ],
    }

    def test_inbound_allowlist_and_rejection_recorded(self):
        self.transport.script["getUpdates"] = (200, json.dumps(self.TELEGRAM_UPDATES))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        feed = self.hub.receive("telegram")
        states = {event["state"]: event for event in feed["events"]}
        self.assertIn("rejected_not_allowed", states)
        self.assertIn("received", states)
        equal = {event["sender"] for event in feed["events"]}
        self.assertEqual(equal, {"42", "777"})

    def test_replay_protection_prevents_duplicate_processing(self):
        self.transport.script["getUpdates"] = (200, json.dumps(self.TELEGRAM_UPDATES))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        first = self.hub.receive("telegram")
        second = self.hub.receive("telegram")
        self.assertEqual(len(first["events"]), 2)
        self.assertEqual(second["events"], [])
        history = self.hub.history()
        self.assertEqual(len([m for m in history["messages"] if m["channel"] == "telegram"]), 2)

    def test_providers_without_inbound_polling_are_honest(self):
        self.hub.configure("slack", {"bot_token": "xoxb", "allowed_channel": "C1"})
        with self.assertRaises(HubError) as caught:
            self.hub.receive("slack")
        self.assertIn("cannot poll", str(caught.exception))

    def test_inbound_transport_failure_is_reported_not_hidden(self):
        self.transport.script["getUpdates"] = (502, json.dumps({"ok": False}))
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        with self.assertRaises(HubError):
            self.hub.receive("telegram")
        status = self.hub.status()
        self.assertEqual(status["channels"]["telegram"]["failures"], 1)


class AuditAndStatusTests(Base):
    def test_history_limit_bounded(self):
        with self.assertRaises(HubError):
            self.hub.history(limit=0)
        with self.assertRaises(HubError):
            self.hub.history(limit=201)

    def test_connected_state_requires_successful_activity_not_config_only(self):
        self.hub.configure("telegram", {"bot_token": "123", "allowed_chat_id": "42"})
        self.assertEqual(self.hub.status()["channels"]["telegram"]["state"],
                         "configured, untested")
        self.transport.script["sendMessage"] = (200, json.dumps(
            {"ok": True, "result": {"message_id": 9}}))
        approval = self.approve("telegram", "42", "Hello")
        self.hub.send("telegram", approval["approval_id"])
        self.assertEqual(self.hub.status()["channels"]["telegram"]["state"], "connected")


if __name__ == "__main__":
    unittest.main()
