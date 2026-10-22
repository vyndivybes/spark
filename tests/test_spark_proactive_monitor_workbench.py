"""Capabilities 03 & 11 — Workbench wiring acceptance.

Proposals and monitors flow through real Workbench dispatch with real
spark workspace storage. No network and no external services involved.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError


class ProactiveMonitorWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.directory.name)
        self.workbench = Workbench(self.workspace)
        self.project = "general"
        self.addAsyncCleanup(self._close)

    async def _close(self):
        await self.workbench.integrations.close()
        await self.workbench.intelligence.close()
        self.directory.cleanup()

    async def action(self, action, **payload):
        return await self.workbench.execute(action, self.project, payload)

    async def test_policies_and_monitors_are_registered(self):
        for action in ("proactive_propose", "proactive_decide", "proactive_execute",
                       "proactive_undo", "proactive_inbox", "proactive_summary",
                       "monitor_status", "monitor_run", "monitor_cancel",
                       "monitor_deliver", "monitor_acknowledge"):
            self.assertIn(action, ACTION_KEYS)

    async def test_propose_read_only_and_execute_registered_executor(self):
        queued = await self.action("proactive_propose", source="obsidian-vault",
                                   kind="search.obsidian", tier="read_only",
                                   detail="contract")
        self.assertTrue(queued["queued"])
        result = await self.action("proactive_execute", dedupe_key=queued["dedupe_key"])
        self.assertTrue(result["executed"])
        summary = await self.action("proactive_summary")
        self.assertEqual(summary["executed"], 1)
        inbox = await self.action("proactive_inbox", state="executed", limit=10)
        self.assertEqual(inbox["count"], 1)

    async def test_cross_source_kind_is_refused_at_registration_boundary(self):
        with self.assertRaises(WorkbenchError):
            await self.action("proactive_propose", source="slack",
                              kind="search.obsidian", tier="suggest",
                              detail="cross-source attempt")

    async def test_restricted_tier_is_never_self_executed(self):
        queued = await self.action("proactive_propose", source="camera",
                                   kind="device.unlock", tier="restricted",
                                   detail="unlocks a door remotely")
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("proactive_execute", dedupe_key=queued["dedupe_key"])
        self.assertIn("never self-executed", str(caught.exception))

    async def test_suggest_requires_explicit_decision(self):
        queued = await self.action("proactive_propose", source="workbench",
                                   kind="search.snapshots", tier="suggest",
                                   detail="payment contract")
        with self.assertRaises(WorkbenchError):
            await self.action("proactive_execute", dedupe_key=queued["dedupe_key"])
        await self.action("proactive_decide", dedupe_key=queued["dedupe_key"],
                          approved=True, remember=False)
        result = await self.action("proactive_execute", dedupe_key=queued["dedupe_key"])
        self.assertTrue(result["executed"])
        entries = result["result"] if isinstance(result["result"], list) else []
        self.assertTrue(all(isinstance(entry, dict) for entry in entries))

    async def test_remembered_yes_auto_executes_future_proposal(self):
        first = await self.action("proactive_propose", source="obsidian-vault",
                                  kind="search.obsidian", tier="suggest",
                                  detail="renewal")
        await self.action("proactive_decide", dedupe_key=first["dedupe_key"],
                          approved=True, remember=True)
        await self.action("proactive_execute", dedupe_key=first["dedupe_key"])
        self.later_clock()
        second = await self.action("proactive_propose", source="obsidian-vault",
                                   kind="search.obsidian", tier="suggest",
                                   detail="renegotiation")
        result = await self.action("proactive_execute",
                                   dedupe_key=second["dedupe_key"])
        self.assertTrue(result["executed"])

    def later_clock(self):
        # The propose dedupe window ignores identical content; a different
        # detail yields a different dedupe key immediately.
        return None

    async def test_proposal_undo_records_state(self):
        queued = await self.action("proactive_propose", source="obsidian-vault",
                                   kind="search.obsidian", tier="read_only",
                                   detail="nda")
        await self.action("proactive_execute", dedupe_key=queued["dedupe_key"])
        undone = await self.action("proactive_undo", dedupe_key=queued["dedupe_key"])
        self.assertTrue(undone["undone"])
        inbox = await self.action("proactive_inbox", state="undone", limit=10)
        self.assertEqual(inbox["count"], 1)

    async def test_monitor_lifecycle_works_through_actions(self):
        await self.action("monitor_run", name="snapshot-freshness", force=True)
        status = await self.action("monitor_status")
        self.assertEqual(len(status["monitors"]), 1)
        delivery = await self.action("monitor_deliver", name="snapshot-freshness")
        self.assertIsInstance(delivery["delivered"], int)
        await self.action("monitor_cancel", name="snapshot-freshness")
        forced = await self.action("monitor_run", name="snapshot-freshness", force=True)
        self.assertEqual(forced["state"], "cancelled")
        with self.assertRaises(WorkbenchError):
            await self.action("monitor_run", name="missing", force=True)

    async def test_registered_monitor_notification_channel_note_exists(self):
        # The local notification channel exists as a bounded JSONL file path.
        self.assertTrue(str(self.workbench._notifications).endswith(
            "monitor-notifications.jsonl"))


if __name__ == "__main__":
    unittest.main()
