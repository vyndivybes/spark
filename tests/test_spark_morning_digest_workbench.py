"""Capability 01 — Workbench/UI wiring acceptance for the Morning Digest.

Runs the digest actions through the real Workbench dispatch with a real
SparkWorkspace and IntegrationSync storage; no network or OAuth involved.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError


class DigestWorkbenchWiringTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_digest_actions_are_registered(self):
        for action in ("digest_status", "digest_run", "digest_history", "digest_ack",
                       "digest_speech", "digest_speak", "digest_configure"):
            self.assertIn(action, ACTION_KEYS)

    async def test_digest_status_reports_evidence_gates_and_tts_policy(self):
        status = await self.action("digest_status")
        self.assertEqual(status["schema"], "spark.morning_digest.v1")
        self.assertIsNone(status["latest_run"])
        self.assertEqual(status["final_states"], ("completed", "failed"))
        self.assertTrue(status["tts"]["requires_explicit_request"])
        self.assertFalse(status["tts"]["network_free"])
        self.assertEqual(status['tts']['engine'], 'SPARK Gemini Live voice')

    async def test_digest_run_through_unconfigured_sources_is_final_failed(self):
        result = await self.action("digest_run")
        self.assertEqual(result["status"], "failed")
        for service in ("gmail", "google-calendar", "google-drive"):
            self.assertEqual(result["sources"][service]["state"], "not_configured")
        history = await self.action("digest_history", limit=5)
        self.assertEqual(history["count"], 1)
        self.assertEqual(history["runs"][0]["status"], "failed")

    async def test_digest_ack_rejected_until_a_digest_completed(self):
        await self.action("digest_run")
        with self.assertRaises(WorkbenchError):
            await self.action("digest_ack", digest="")

    async def test_digest_speech_below_failure_is_blocked(self):
        await self.action("digest_run")
        with self.assertRaises(WorkbenchError):
            await self.action("digest_speech", digest="")

    async def test_digest_configure_validates_schedule_and_defaults_news_off(self):
        status = await self.action("digest_configure", schedule_ist="08:30",
                                   news_enabled=False, news_url="")
        self.assertEqual(status["schedule_ist"], "08:30")
        self.assertFalse(status["news_enabled"])
        with self.assertRaises(WorkbenchError):
            await self.action("digest_configure", schedule_ist="7:5",
                              news_enabled=False, news_url="")

    async def test_digest_speech_payload_projection_requires_completed_digest(self):
        # speak() on an unconfigured account must not fabricate speech.
        await self.action("digest_run")
        with self.assertRaises(WorkbenchError):
            await self.action("digest_speak", digest="")


if __name__ == "__main__":
    unittest.main()
