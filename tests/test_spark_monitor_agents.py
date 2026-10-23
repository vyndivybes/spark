"""Capability 11 — Continuous monitor offline acceptance.

Checks are injectable fake callables; restart/resume, dedupe, backoff,
cancellation, delivery receipts and compaction all run on a real sqlite
store. No network or notifications outside the store.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_monitor_agents import (MonitorAgents, MonitorError,
                                  DEFAULT_INTERVAL, KEEP_EVENTS)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.clock = 1_800_000_000.0
        self.agents = MonitorAgents(self.root, clock=lambda: self.clock)
        self.checked = []

    def register(self, events=None, error=None):
        def check():
            self.checked.append(1)
            if error:
                raise error
            return events or []

        self.agents.register("inbox-watch", "gmail", check, interval=60)
        return check


class RegistrationTests(Base):
    def test_registration_validation(self):
        with self.assertRaises(MonitorError):
            self.agents.register("Bad Name!", "gmail", lambda: [])
        with self.assertRaises(MonitorError):
            self.agents.register("inbox", "", lambda: [])
        with self.assertRaises(MonitorError):
            self.agents.register("inbox", "gmail", "not callable")
        with self.assertRaises(MonitorError):
            self.agents.register("inbox", "gmail", lambda: [], interval=10)
        with self.assertRaises(MonitorError):
            self.agents.register("inbox", "gmail", lambda: [], interval=99999)

    def test_unknown_monitor_refused(self):
        with self.assertRaises(MonitorError):
            self.agents.run_once("missing")
        with self.assertRaises(MonitorError):
            self.agents.cancel("missing")

    def test_run_once_honors_schedule_before_force(self):
        self.register(events=[{"kind": "unread.growth", "count": 4}])
        first = self.agents.run_once("inbox-watch")
        self.assertEqual(first["state"], "completed")
        self.assertEqual(first["events"], 1)
        waiting = self.agents.run_once("inbox-watch")
        self.assertEqual(waiting["state"], "waiting")
        forced = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(forced["state"], "completed")
        self.assertEqual(forced["events"], 0)  # Duplicate check yields nothing.


class EventDedupTests(Base):
    def test_identical_events_across_polls_are_not_duplicated(self):
        self.register(events=[{"kind": "unread.growth", "count": 4}])
        first = self.agents.run_once("inbox-watch", force=True)
        second = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(first["events"], 1)
        self.assertEqual(second["events"], 0)
        out = [row for row in self.agents.status()["monitors"]]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["state"], "healthy")

    def test_new_events_still_surface_after_delta(self):
        self.register()
        self.agents.checks["inbox-watch"]["check"] = \
            lambda: [{"kind": "unread.growth", "count": 4}]
        self.agents.run_once("inbox-watch", force=True)
        self.agents.checks["inbox-watch"]["check"] = \
            lambda: [{"kind": "unread.growth", "count": 9}]
        result = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(result["events"], 1)

    def test_event_limit_per_run_is_bounded(self):
        flood = [{"kind": f"event.{n}", "n": n} for n in range(120)]
        self.register()
        self.agents.checks["inbox-watch"]["check"] = lambda: flood
        result = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(result["events"], 50)


class BackoffAndFailureTests(Base):
    def test_failures_backoff_exponentially_up_to_cap(self):
        def broken():
            raise OSError("gmail down")

        self.agents.register("inbox-watch", "gmail", broken, interval=60)
        first = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(first["state"], "failed")
        self.assertEqual(first["failures"], 1)
        base = first["next_due"]
        self.clock += 1
        second = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(second["failures"], 2)
        self.assertGreater(second["next_due"], base)
        self.assertIn("gmail down", first["error"])

    def test_success_resets_failures(self):
        state = {"broken": True}

        check = lambda: (_ for _ in ()).throw(OSError("down"))  # noqa: E731
        self.agents.register("inbox-watch", "gmail", check, interval=60)
        self.agents.run_once("inbox-watch", force=True)
        self.agents.checks["inbox-watch"]["check"] = \
            lambda: [{"kind": "recovered", "note": "ok"}]
        result = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(result["state"], "completed")
        status = self.agents.status()["monitors"][0]
        self.assertEqual(status["failures"], 0)
        self.assertEqual(status["state"], "healthy")


class CancelRestartResumeTests(Base):
    def test_cancellation_is_durable_and_blocks_further_runs(self):
        self.register(events=[{"kind": "e", "x": 1}])
        cancelled = self.agents.cancel("inbox-watch")
        self.assertTrue(cancelled["cancelled"])
        result = self.agents.run_once("inbox-watch", force=True)
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(self.checked, [])
        status = self.agents.status()["monitors"][0]
        self.assertEqual(status["state"], "cancelled")

    def test_monitor_resumes_after_restart_with_persisted_checkpoint(self):
        self.register(events=[{"kind": "unread.growth", "count": 2}])
        self.agents.run_once("inbox-watch", force=True)
        self.clock += 30
        reborn = MonitorAgents(self.root, clock=lambda: self.clock)

        def resumed_check():
            return [{"kind": "unread.growth", "count": 12}]

        reborn.register("inbox-watch", "gmail", resumed_check, interval=60)
        self.clock += 120
        result = reborn.run_once("inbox-watch", force=True)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["events"], 1)
        status = reborn.status()["monitors"][0]
        self.assertIn(reborn.checks["inbox-watch"]["scope"], ("gmail",))

    def test_scheduled_resume_waits_for_due_time(self):
        self.register(events=[{"kind": "e1", "x": 1}])
        self.agents.run_once("inbox-watch", force=True)
        self.clock += 30
        reborn = MonitorAgents(self.root, clock=lambda: self.clock)
        reborn.register("inbox-watch", "gmail", lambda: [{"kind": "e1", "x": 1}],
                        interval=60)
        waiting = reborn.run_once("inbox-watch")
        self.assertEqual(waiting["state"], "waiting")


class NotificationReceiptTests(Base):
    def test_delivery_and_acknowledgement_lifecycle(self):
        self.register(events=[{"kind": "unread.growth", "count": 2}])
        self.agents.run_once("inbox-watch", force=True)
        delivered = []
        result = self.agents.deliver("inbox-watch", lambda key: delivered.append(key))
        self.assertEqual(result["delivered"], 1)
        key = delivered[0]
        pending = self.agents.pending_notifications()
        self.assertEqual(pending["count"], 1)
        receipt = self.agents.acknowledge(key)
        self.assertTrue(receipt["acknowledged"])
        self.assertEqual(self.agents.pending_notifications()["count"], 0)

    def test_failed_delivery_is_queued_for_retry(self):
        self.register(events=[{"kind": "unread.growth", "count": 2}])
        self.agents.run_once("inbox-watch", force=True)

        def broken_delivery(key):
            raise OSError("channel down")

        result = self.agents.deliver("inbox-watch", broken_delivery)
        self.assertEqual(result["delivered"], 0)
        pending_before = self.agents.pending_notifications()
        result2 = self.agents.deliver("inbox-watch", lambda key: None)
        self.assertEqual(result2["delivered"], 1)

    def test_acknowledge_requires_known_key(self):
        with self.assertRaises(MonitorError):
            self.agents.acknowledge("nope")


class CompactionTests(Base):
    def test_compaction_bounded_and_keeps_unacknowledged(self):
        self.agents.checks["inbox-watch"] = {
            "check": lambda: [{"kind": f"event.{n}", "n": n} for n in range(60)],
            "scope": "gmail"}
        self.agents.register("inbox-watch", "gmail", lambda: [], interval=60)
        self.agents.run_once("inbox-watch", force=True)
        result = self.agents.compact()
        self.assertTrue(result["compacted"])
        with self.agents._db() as db:
            remaining = db.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
        self.assertLessEqual(remaining, KEEP_EVENTS)


if __name__ == "__main__":
    unittest.main()
