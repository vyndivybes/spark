"""Capability 01 Morning Digest — offline acceptance tests.

Real API-shaped snapshot payloads from the PR #48 read-only Google readers;
no network, OAuth or speech execution. Live account acceptance requires the
founder's authenticated Windows session and is documented, not faked here.
"""
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_morning_digest import (DigestEngine, DigestError, NewsSource,
                                  ist_date)


def stale(count):
    return time.time() - count


class FakeSync:
    """Mirrors IntegrationSync.briefing() output shapes exactly."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def briefing(self):
        self.calls += 1
        return self.payload


def base_briefing(now):
    return {"timezone": "Asia/Kolkata", "date": ist_date(now),
            "generated_at": now, "mode": "cached Google reads, not live",
            "sources": {"gmail": {"state": "current", "last_success": now,
                                  "stale": False, "error": None,
                                  "account": "owner@example.com"},
                        "google-calendar": {"state": "current", "last_success": now,
                                            "stale": False, "error": None},
                        "google-drive": {"state": "failed", "last_success": None,
                                         "stale": True,
                                         "error": "Read unavailable; check source sign-in."}},
            "emails": [{"id": "abc123", "from": "Sender <s@example.org>",
                        "subject": "Urgent: payment failed", "snippet": "Act now",
                        "unread": True, "priority": "urgent", "reason": "Urgency phrase",
                        "reply_status": "not_verified",
                        "url": "https://mail.google.com/mail/?authuser=owner@example.com"}],
            "events": [{"id": "e1", "title": "Standup", "start": "2026-10-21T09:00:00+05:30",
                        "end": "2026-10-21T09:30:00+05:30", "all_day": False,
                        "url": "https://calendar.google.com/e1",
                        "response_status": "needsAction", "overlap": False}],
            "documents": [{"id": "d1", "name": "NDA review.pdf", "description": "",
                           "modified": "2026-10-20T10:00:00Z",
                           "url": "https://drive.google.com/d1",
                           "review_candidate": True}],
            "attention_count": 1, "read_only": True}


class NotConfiguredSync:
    def briefing(self):
        return {"timezone": "Asia/Kolkata", "date": ist_date(), "generated_at": time.time(),
                "sources": {"gmail": {"state": "not_configured", "message": "Register the reader."}},
                "emails": [], "events": [], "documents": [], "attention_count": 0,
                "read_only": True}


class DigestCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = str(Path(self.enterContext(dir_hook())))
        self.now = time.time()

    def run_engine(self, sync, **kwargs):
        engine = DigestEngine(self.temp, sync, clock=lambda: self.now, **kwargs)
        return engine, engine.run()

    def test_digest_completes_with_triage_links_and_sources(self):
        sync = FakeSync(base_briefing(self.now))
        engine, result = self.run_engine(sync)
        self.assertEqual(sync.calls, 1)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["last_fetched"], self.now)
        priorities = [item["priority"] for item in result["triage"]]
        self.assertEqual(priorities[0], "urgent")
        self.assertTrue(all(item["url"] for item in result["triage"]))
        self.assertTrue(all(item["source"] for item in result["triage"]))
        self.assertEqual(result["timezone"], "Asia/Kolkata")
        self.assertIn(result["status"], ("completed", "failed"))

    def test_drive_failure_is_reported_not_hidden(self):
        sync = FakeSync(base_briefing(self.now))
        _, result = self.run_engine(sync)
        drive = result["sources"]["google-drive"]
        self.assertEqual(drive["state"], "failed")
        self.assertTrue(drive["stale"])
        self.assertIsNotNone(drive["error"])
        self.assertEqual(result["status"], "completed")

    def test_all_sources_unavailable_ends_in_final_failed_state(self):
        engine = DigestEngine(self.temp, NotConfiguredSync(), clock=lambda: self.now)
        result = engine.run()
        self.assertEqual(result["status"], "failed")
        self.assertIn("not_configured", json.dumps(result["sources"]))
        self.assertEqual(engine.status()["latest_run"]["status"], "failed")

    def test_invalid_briefing_fails_fast_with_recorded_error(self):
        class BrokenSync:
            def briefing(self):
                raise ValueError("Google API read failed")

        engine = DigestEngine(self.temp, BrokenSync(), clock=lambda: self.now)
        result = engine.run()
        self.assertEqual(result["status"], "failed")
        self.assertIn("could not be composed", result["sources"]["message"])
        self.assertEqual(engine.history()["runs"][0]["status"], "failed")

    def test_stale_source_is_flagged_with_last_success(self):
        expected = stale(4000)
        payload = base_briefing(self.now)
        payload["sources"]["gmail"].update({"last_success": expected, "stale": True})
        engine = DigestEngine(self.temp, FakeSync(payload), clock=lambda: self.now)
        result = engine.run()
        gmail = result["sources"]["gmail"]
        self.assertTrue(gmail["stale"])
        self.assertAlmostEqual(gmail["last_success"], expected, places=3)

    def test_error_state_captures_403_as_forbidden(self):
        payload = {"sources": {"gmail": {"state": "failed",
                                         "error": "Google API 403 permission denied"}},
                   "emails": [], "events": [], "documents": []}
        engine = DigestEngine(self.temp, FakeSync(payload), clock=lambda: self.now)
        result = engine.run()
        self.assertEqual(result["sources"]["gmail"]["state"], "forbidden")

    def test_reply_status_is_never_asserted(self):
        engine, result = self.run_engine(FakeSync(base_briefing(self.now)))
        sample = json.dumps(result["emails"])
        self.assertIn("not_verified", sample)
        self.assertNotIn('"replied"', sample)

    def test_delta_compares_with_existing_previous_digest(self):
        yesterday = self.now - 86400
        payload = base_briefing(yesterday)
        engine = DigestEngine(self.temp, FakeSync(payload), clock=lambda: yesterday)
        engine.run()
        engine2 = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        result = engine2.run()
        self.assertEqual(result["delta"]["previous"]["emails"], 1)
        self.assertEqual(result["delta"]["today"]["emails"], 1)
        self.assertEqual(result["delta"]["email_change"], 0)


class PersistedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = str(Path(self.enterContext(dir_hook())))
        self.now = time.time()

    def test_history_is_persisted_per_day(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now - 86400)),
                              clock=lambda: self.now - 86400)
        engine.run()
        engine2 = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        engine2.run()
        history = engine2.history(limit=5)
        self.assertEqual(history["count"], 2)
        dates = [run["date"] for run in history["runs"]]
        self.assertEqual(len(set(dates)), 2)

    def test_history_limit_is_bounded(self):
        engine = DigestEngine(self.temp, NotConfiguredSync(), clock=lambda: self.now)
        with self.assertRaises(DigestError):
            engine.history(limit=0)
        with self.assertRaises(DigestError):
            engine.history(limit=61)

    def test_same_day_run_replaces_not_duplicates(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        engine.run()
        engine.run()
        self.assertEqual(engine.history()["count"], 1)


class AcknowledgementAndSpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = str(Path(self.enterContext(dir_hook())))
        self.now = time.time()

    def test_acknowledge_records_explicit_receipt(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        engine.run()
        receipt = engine.acknowledge()
        self.assertTrue(receipt["acknowledged"])
        status = engine.status()
        self.assertTrue(status["latest_run"]["acknowledged"])
        self.assertEqual(status["latest_run"]["acknowledged"] is True,
                         bool(status["latest_run"].get("acknowledged_at")))

    def test_acknowledge_requires_completed_digest(self):
        engine = DigestEngine(self.temp, NotConfiguredSync(), clock=lambda: self.now)
        engine.run()
        with self.assertRaises(DigestError):
            engine.acknowledge()

    def test_speech_command_is_local_and_injection_safe(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        engine.run()
        payload = engine.speech_payload()
        self.assertEqual(payload["engine"], "Windows System.Speech")
        self.assertTrue(payload["network_free"])
        joined = " ".join(payload["command"])
        self.assertNotIn("`", joined)
        self.assertNotIn('"', joined)

    def test_speak_records_final_outcome_with_fake_runner(self):
        def runner(command, timeout):
            return 0

        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)),
                              clock=lambda: self.now, runner=runner)
        engine.run()
        result = engine.speak()
        self.assertTrue(result["spoken"])
        self.assertEqual(engine.history()["runs"][0]["speech"], "spoken")

    def test_speak_failure_marks_failed_state(self):
        def runner(command, timeout):
            raise OSError("powershell not reachable")

        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)),
                              clock=lambda: self.now, runner=runner)
        engine.run()
        result = engine.speak()
        self.assertFalse(result["spoken"])
        self.assertEqual(engine.history()["runs"][0]["speech"], "failed")

    def test_speak_rejected_for_failed_digest(self):
        engine = DigestEngine(self.temp, NotConfiguredSync(), clock=lambda: self.now)
        engine.run()
        with self.assertRaises(DigestError):
            engine.speech_payload()


class ScheduleAndTasksTests(unittest.TestCase):
    def setUp(self):
        self.temp = str(Path(self.enterContext(dir_hook())))
        self.now = time.time()

    def test_schedule_is_validated_and_persisted(self):
        engine = DigestEngine(self.temp, NotConfiguredSync(), clock=lambda: self.now)
        engine.configure(schedule_ist="08:30", news_enabled=False)
        self.assertEqual(engine.scheduled_time(), "08:30")
        self.assertFalse(engine.status()["news_enabled"])
        with self.assertRaises(DigestError):
            engine.configure(schedule_ist="25:00")
        with self.assertRaises(DigestError):
            engine.configure(schedule_ist="not a time")

    def test_tasks_source_states_are_individual(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)),
                              clock=lambda: self.now, tasks=lambda project: [{"id": 1, "title": "File NDA"}])
        result = engine.run()
        self.assertEqual(result["sources"]["tasks"]["state"], "current")
        self.assertEqual(result["tasks"][0]["title"], "File NDA")

    def test_missing_task_source_is_not_configured(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        result = engine.run()
        self.assertEqual(result["sources"]["tasks"]["state"], "not_configured")

    def test_news_disabled_by_default(self):
        engine = DigestEngine(self.temp, FakeSync(base_briefing(self.now)), clock=lambda: self.now)
        self.assertFalse(engine.status()["news_enabled"])
        self.assertIsNone(engine.status()["latest_run"])

    def test_news_url_is_validated(self):
        with self.assertRaises(DigestError):
            NewsSource("file:///etc/passwd")
        with self.assertRaises(DigestError):
            NewsSource("")

    def test_news_parsing_is_bounded_and_typed(self):
        source = NewsSource("https://news.local/rss")
        class FakeResponse:
            def __init__(self, blob):
                self.blob = blob
            def read(self, amount):
                return self.blob[:amount]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        xml = ("<rss><channel><item><title>Market opens up</title>"
               "<link>https://news.local/1</link><pubDate>Wed, 21 Oct 2026</pubDate></item>"
               "<item><title>Second story</title></item></channel></rss>").encode()
        def fake_urlopen(request, timeout):
            return FakeResponse(xml)
        import spark_morning_digest as module
        original = module.urlopen
        module.urlopen = fake_urlopen
        try:
            feed = source.fetch()
        finally:
            module.urlopen = original
        self.assertEqual(feed["source"], "rss-news")
        self.assertEqual(feed["items"][0]["title"], "Market opens up")
        self.assertEqual(feed["items"][0]["url"], "https://news.local/1")
        self.assertEqual(len(feed["items"]), 2)


def dir_hook():
    import tempfile
    return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
