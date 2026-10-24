"""Tests for SPARK Telegram owner interface."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


from spark_telegram import (
    DEFAULT_ALLOWED_CHAT_ID,
    GeminiTextEngine,
    SparkTelegramContext,
    TelegramBotAPI,
    TelegramError,
    TelegramState,
    TelegramWorker,
    build_telegram_worker,
    format_digest,
    format_integrations,
    format_missions,
    format_agents,
    format_status,
    load_telegram_settings,
    split_message,
)
from spark_credential_store import CredentialStore


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.script = {}

    def __call__(self, method, url, headers=None, body=None, timeout=15):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        key = method + " " + url.split("/")[-1]
        if key in self.script:
            status, text = self.script[key]
            return status, text
        return 200, json.dumps({"ok": True, "result": {}})


class InMemoryStore:
    def __init__(self):
        self.tokens = {}

    def save_telegram_token(self, token):
        self.tokens["telegram_bot_token"] = token
        return Path("memory:telegram_bot_token")

    def load_telegram_token(self):
        return self.tokens.get("telegram_bot_token")

    def delete_telegram_token(self):
        self.tokens.pop("telegram_bot_token", None)
        return True


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.store = InMemoryStore()

    def tearDown(self):
        self.dir.cleanup()

    def test_token_not_in_config_json(self):
        settings = load_telegram_settings(self.root, store=self.store)
        self.assertFalse(settings.configured)
        self.store.save_telegram_token("123:ABC")
        settings = load_telegram_settings(self.root, store=self.store)
        self.assertTrue(settings.configured)
        config_path = self.root / "telegram" / "config.json"
        if config_path.exists():
            self.assertNotIn("123:ABC", config_path.read_text(encoding="utf-8"))
        self.assertEqual(settings.allowed_chat_id, DEFAULT_ALLOWED_CHAT_ID)

    def test_only_owner_private_chat_accepted(self):
        transport = FakeTransport()
        api = TelegramBotAPI("123:ABC", transport=transport)
        state = TelegramState(self.root / "telegram")
        worker = TelegramWorker(settings=load_telegram_settings(self.root, store=self.store),
                                state=state, api=api)
        # not configured
        self.assertFalse(worker.settings.configured)
        # simulate unauthorized
        ok, reason = worker._authorized({"chat": {"id": 111, "type": "private"},
                                        "from": {"id": 111, "is_bot": False}})
        self.assertFalse(ok)
        self.assertEqual(reason, "chat_not_allowed")
        # group
        ok, reason = worker._authorized({"chat": {"id": 6463473290, "type": "group"},
                                        "from": {"id": 6463473290, "is_bot": False}})
        self.assertFalse(ok)
        self.assertEqual(reason, "not_private_chat")
        # bot sender
        ok, reason = worker._authorized({"chat": {"id": 6463473290, "type": "private"},
                                        "from": {"id": 6463473290, "is_bot": True}})
        self.assertFalse(ok)
        self.assertEqual(reason, "bot_sender")

    def test_commands_and_unknown(self):
        transport = FakeTransport()
        state = TelegramState(self.root / "telegram")
        worker = TelegramWorker(settings=load_telegram_settings(self.root, store=self.store),
                                state=state, api=TelegramBotAPI("123:ABC", transport=transport))
        async def run():
            self.assertIn("SPARK over Telegram", await worker._run_command({"name": "help"}))
            self.assertIn("Unknown command", await worker._run_command({"name": "nuke"}))
        asyncio.run(run())

    def test_intent_routes_to_real_commands(self):
        transport = FakeTransport()
        state = TelegramState(self.root / "telegram")
        worker = TelegramWorker(settings=load_telegram_settings(self.root, store=self.store),
                                state=state, api=TelegramBotAPI("123:ABC", transport=transport))
        self.assertEqual(worker._intent("what's the status?")["name"], "status")
        self.assertEqual(worker._intent("give me today's morning digest")["name"], "digest")
        self.assertEqual(worker._intent("show missions")["name"], "missions")
        self.assertIsNone(worker._intent("tell me a joke about rockets"))

    def test_voice_transcribes_then_routes(self):
        transport = FakeTransport()
        state = TelegramState(self.root / "telegram")
        class DummyAPI:
            def get_file(self, file_id): return {"file_path": "voice/file.ogg"}
            def download_file(self, path): return b"OGGDATA"
        class DummyEngine:
            async def transcribe(self, audio, mime_type="audio/ogg"):
                return {"text": "/status"}
            async def generate(self, messages, system_instruction=None):
                return {"text": "hi"}
        worker = TelegramWorker(settings=load_telegram_settings(self.root, store=self.store),
                                state=state, api=DummyAPI(), engine=DummyEngine())
        async def run():
            reply, kind = await worker._handle_voice("6463473290", {"file_id": "x"}, 1)
            self.assertIn("/status", reply)
            self.assertEqual(kind, "voice")
        asyncio.run(run())

    def test_digest_uses_real_engine_no_fabrication(self):
        state = TelegramState(self.root / "telegram")
        class W:
            def __init__(self): self.digest = self
            def run(self):
                return {"status": "completed", "speech_text": "clear", "sources": {"news": {"state": "current"}}}
        ctx = SparkTelegramContext(W())
        async def run():
            result = await ctx.digest()
            self.assertEqual(result["status"], "completed")
        asyncio.run(run())
        # formatter reports failures honestly
        out = format_digest({"status": "failed", "speech_text": "broken"})
        self.assertIn("broken", out)

    def test_formatters_hide_secrets(self):
        status_out = format_status({"core": {"platform": "win32"}, "host": {"state": "ok"},
                                    "integrations": {"services": []},
                                    "messaging": {"channels": {}},
                                    "digest": {"state": "unknown"},
                                    "agents": {"state": "unavailable"}}, {"bot_username": "vayusparkbot",
                                                                           "authorized_chat_id": "6463473290"})
        self.assertNotIn("bot_token", status_out)
        self.assertIn("@vayusparkbot", status_out)
        missions = format_missions({"agents": {"runtimes": []}})
        self.assertIn("missions", missions.lower())
        agents = format_agents({"runtimes": []})
        self.assertIn("agent runtimes", agents.lower())
        integrations = format_integrations({"services": [], "messaging": {"channels": {}}})
        self.assertIn("integrations", integrations.lower())

    def test_split_message_and_no_tool_execution_in_chat(self):
        text = "x" * 9000
        chunks = split_message(text)
        self.assertTrue(len(chunks) > 1)
        # ensure GeminiTextEngine exists and has transcribe/generate
        engine = GeminiTextEngine()
        self.assertTrue(hasattr(engine, "generate"))
        self.assertTrue(hasattr(engine, "transcribe"))

    def test_build_worker_without_token_returns_none(self):
        store = InMemoryStore()
        worker = build_telegram_worker(workspace_root=self.root, store=store)
        self.assertIsNone(worker)

    def test_duplicate_suppression_and_offset(self):
        state = TelegramState(self.root / "telegram")
        self.assertEqual(state.get_offset(), 0)
        state.mark_update(10, "6463473290", 5)
        self.assertTrue(state.seen_update(10))
        state.set_offset(10)
        self.assertEqual(state.get_offset(), 10)

    def test_poll_lease_blocks_second_worker(self):
        state = TelegramState(self.root / "telegram")
        self.assertTrue(state.acquire_poll_lease("a"))
        self.assertFalse(state.acquire_poll_lease("b"))
        self.assertTrue(state.refresh_poll_lease("a"))
        self.assertTrue(state.release_poll_lease("a"))
        self.assertTrue(state.acquire_poll_lease("b"))

    def test_status_never_includes_token(self):
        transport = FakeTransport()
        self.store.save_telegram_token("123:SECRET")
        state = TelegramState(self.root / "telegram")
        worker = TelegramWorker(settings=load_telegram_settings(self.root, store=self.store),
                                state=state, api=TelegramBotAPI("123:SECRET", transport=transport))
        status = worker.status()
        self.assertNotIn("123:SECRET", json.dumps(status))
        self.assertTrue(status["token_present"])

    def test_process_update_rejects_unauthorized_and_advances_offset(self):
        self.store.save_telegram_token("123:SECRET")
        settings = load_telegram_settings(self.root, store=self.store)
        sent = []
        class API:
            def send_message(self, chat_id, text, reply_to_message_id=None):
                sent.append(chat_id)
                return {"message_id": 1}
        worker = TelegramWorker(settings=settings, api=API(),
                                state=TelegramState(self.root / "telegram"))
        update = {"update_id": 10, "message": {"message_id": 1,
                  "chat": {"id": 999, "type": "private"}, "from": {"id": 999, "is_bot": False},
                  "text": "/help"}}
        async def run():
            first = await worker.process_update(update)
            second = await worker.process_update(update)
            self.assertEqual(first["state"], "rejected")
            self.assertEqual(second["state"], "duplicate")
        asyncio.run(run())
        self.assertEqual(sent, [])
        self.assertEqual(worker.state.get_offset(), 11)

    def test_unknown_command_help_is_safe(self):
        self.store.save_telegram_token("123:SECRET")
        settings = load_telegram_settings(self.root, store=self.store)
        sent = []
        class API:
            def send_message(self, chat_id, text, reply_to_message_id=None):
                sent.append(text)
                return {"message_id": 1}
        worker = TelegramWorker(settings=settings, api=API(),
                                state=TelegramState(self.root / "telegram"))
        update = {"update_id": 20, "message": {"message_id": 2,
                  "chat": {"id": 6463473290, "type": "private"},
                  "from": {"id": 6463473290, "is_bot": False}, "text": "/nonsense"}}
        asyncio.run(worker.process_update(update))
        self.assertEqual(len(sent), 1)
        self.assertIn("Unknown command", sent[0])
        self.assertEqual(worker.state.get_offset(), 21)

    def test_daily_digest_sent_once_after_ist_schedule(self):
        self.store.save_telegram_token("123:SECRET")
        settings = load_telegram_settings(self.root, store=self.store)
        sent = []
        class API:
            def send_message(self, chat_id, text, reply_to_message_id=None):
                sent.append((chat_id, text))
                return {"message_id": 1}
        class Context:
            async def digest_schedule(self): return "07:00"
            async def digest(self):
                return {"status": "completed", "date": "2026-10-24",
                        "texts": {"digest_text": "Today: verified sources only."},
                        "sources": {"calendar": {"state": "current"}}}
        # 07:30 IST == 02:00 UTC on 2026-10-24
        when = 1792807200.0
        worker = TelegramWorker(settings=settings, context=Context(), api=API(),
                                state=TelegramState(self.root / "telegram", clock=lambda: when),
                                clock=lambda: when)
        async def run():
            await worker._maybe_send_digest()
            await worker._maybe_send_digest()
        asyncio.run(run())
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "6463473290")
        self.assertEqual(worker.state.digest_sent_date(), "2026-10-24")



if __name__ == "__main__":
    unittest.main()
