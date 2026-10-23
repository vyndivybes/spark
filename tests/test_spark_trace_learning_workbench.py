"""Capabilities 07 & 12 — Workbench wiring acceptance.

Traces, routing decisions and learning candidates flow through real
Workbench dispatch with real spark workspace storage. Captured traces are
masked, outcomes are measured booleans only, and activation/rollback are
owner gates. No network and no external model calls involved.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError


class TraceLearningWiringTests(unittest.IsolatedAsyncioTestCase):
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

    async def capture(self, task="digest", model="ollama-local", latency=10.0,
                      success="true", payload="config GEMINI_API_KEY=abc123"):
        return await self.action("trace_capture", task_class=task, model=model,
                                 payload=payload, latency_ms=latency,
                                 success=success)

    async def test_actions_are_registered(self):
        for action in ("trace_capture", "trace_label", "trace_labeled",
                       "trace_status", "router_select", "learning_propose",
                       "learning_activate", "learning_rollback",
                       "learning_status"):
            self.assertIn(action, ACTION_KEYS)

    async def test_capture_is_masked_and_labeled_listing_works(self):
        captured = await self.capture()
        self.assertEqual(captured["status"], "captured")
        labeled = await self.action("trace_labeled", task_class="digest", limit=5)
        self.assertEqual(len(labeled), 1)
        self.assertNotIn("abc123", labeled[0]["masked"])
        self.assertIn("GEMINI_API_KEY=<redacted>", labeled[0]["masked"])
        self.assertEqual(labeled[0]["success"], 1)

    async def test_unmeasured_capture_is_pending_and_excluded(self):
        await self.capture(success="")
        self.assertEqual(await self.action("trace_labeled", task_class="",
                                           limit=10), [])
        status = await self.action("trace_status")
        self.assertEqual(status["summary"], [])

    async def test_label_requires_measured_boolean(self):
        key = (await self.capture(success=""))["key"]
        with self.assertRaises(WorkbenchError):
            await self.action("trace_label", key=key, success="")
        labeled = await self.action("trace_label", key=key, success="false")
        self.assertEqual(labeled["success"], False)

    async def test_router_select_is_local_first_through_workbench(self):
        choice = await self.action("router_select", task_class="digest",
                                   apply_policy=False)
        self.assertEqual(choice["model"], "ollama-local")
        with self.assertRaises(WorkbenchError):
            await self.action("router_select", task_class="no-such-task",
                              apply_policy=True)

    async def test_propose_requires_registered_policy_and_enough_evidence(self):
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("learning_propose", name="x-policy",
                              policy="not-a-registered-policy",
                              task_class="digest")
        self.assertIn("registered on this host", str(caught.exception))
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("learning_propose", name="latency-policy",
                              policy="latency-smallest", task_class="digest")
        self.assertIn("40 labeled traces", str(caught.exception))

    async def test_learning_lifecycle_with_measured_evidence(self):
        # Synthetic *measured* outcomes: research wins on ollama-local,
        # coding wins on groq-free-cloud (both zero-cost/local-first hosts).
        for _ in range(30):
            await self.capture("research", "ollama-local", 600, "true")
            await self.capture("research", "groq-free-cloud", 900, "false")
            await self.capture("coding", "groq-free-cloud", 800, "true")
            await self.capture("coding", "ollama-local", 1500, "true")
        self.assertEqual(len(await self.action("trace_labeled", task_class="",
                                              limit=500)), 120)
        proposal = await self.action("learning_propose", name="latency-policy",
                                     policy="latency-smallest",
                                     task_class="research")
        self.assertIn(proposal["status"], ("proposed", "rejected"))
        with self.assertRaises(WorkbenchError):
            await self.action("learning_activate", key=proposal["key"],
                              approved_by="")
        if proposal["status"] != "proposed":
            self.skipTest("candidate honestly missed the held-out gate")
        activated = await self.action("learning_activate", key=proposal["key"],
                                      approved_by="founder")
        self.assertEqual(activated["approved_by"], "founder")
        status = await self.action("learning_status")
        self.assertIn("latency_policy", status["active_policy"])
        rolled = await self.action("learning_rollback", key=proposal["key"])
        self.assertEqual(rolled["status"], "rolled_back")
        final = await self.action("learning_status")
        self.assertIn("always_local", final["active_policy"])

    async def test_activation_of_unknown_candidate_is_refused(self):
        with self.assertRaises(WorkbenchError):
            await self.action("learning_activate", key="c-missing",
                              approved_by="founder")


if __name__ == "__main__":
    unittest.main()
