"""Capabilities 13, 14, 15 & 16 — Workbench wiring acceptance.

Connector lifecycle, evaluation reports, telemetry refusals and backend
catalog honesty flow through real Workbench dispatch with real spark
workspace storage. No network and no cloud calls in this suite.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError


class CapabilityWorkC1Tests(unittest.IsolatedAsyncioTestCase):
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

    async def test_actions_are_registered(self):
        for action in ("connector_status", "connector_attach_local",
                       "connector_configure", "connector_validate",
                       "connector_read", "connector_freshness",
                       "connector_revoke", "connector_events", "eval_status",
                       "eval_register", "eval_run", "eval_report",
                       "eval_export", "eval_history", "telemetry_status",
                       "telemetry_capture", "telemetry_record",
                       "telemetry_report", "backend_describe",
                       "backend_probe", "backend_generate", "backend_opt_in",
                       "backend_events"):
            self.assertIn(action, ACTION_KEYS)

    # -- capability 13 -----------------------------------------------------
    async def test_local_connector_full_lifecycle(self):
        status = await self.action("connector_status")
        self.assertIn("workspace-search", status["adapters_attached"])
        await self.action("connector_configure", id="workspace-search",
                          account="founder-local", consented=True)
        state = await self.action("connector_validate", id="workspace-search")
        self.assertEqual(state["state"], "account_validated")
        read = await self.action("connector_read", id="workspace-search",
                                 limit=5)
        self.assertEqual(read["state"], "verified_read")
        with self.assertRaises(WorkbenchError):
            await self.action("connector_read", id="workspace-search",
                              limit=5)
        freshness = await self.action("connector_freshness",
                                      id="workspace-search",
                                      stale_after_seconds=86400)
        self.assertEqual(freshness["freshness"], "fresh")
        events = await self.action("connector_events", id="workspace-search",
                                   limit=5)
        self.assertEqual(len(events), 3)

    async def test_configure_without_consent_is_refused(self):
        with self.assertRaises(WorkbenchError):
            await self.action("connector_configure", id="obsidian-vault",
                              account="founder", consented=False)
        with self.assertRaises(WorkbenchError):
            await self.action("connector_read", id="obsidian-vault", limit=2)

    # -- capability 14 -----------------------------------------------------
    async def test_reference_evaluations_run_and_export(self):
        with self.assertRaises(WorkbenchError):
            await self.action("eval_register", name="custom-runner",
                              provenance="x")
        registered = await self.action("eval_register", name="reference-policy",
                                       provenance="")
        self.assertIn("reference policy", registered["provenance"])
        run = await self.action("eval_run", name="reference-policy",
                                suite="agent_tool_policy")
        self.assertEqual(run["pass_rate"], 1.0)
        report = await self.action("eval_report", name="reference-policy",
                                   suite="agent_tool_policy")
        self.assertIn("100%", report)
        exported = await self.action("eval_export", name="reference-policy",
                                     suite="agent_tool_policy")
        self.assertTrue(Path(exported["exported"]).exists())
        with self.assertRaises(WorkbenchError):
            await self.action("eval_run", name="reference-policy",
                              suite="unknown-suite")

    # -- capability 15 -----------------------------------------------------
    async def test_telemetry_records_measured_values_only(self):
        recorded = await self.action("telemetry_record", model="groq",
                                     latency_ms=250, input_tokens=12,
                                     output_tokens=30,
                                     source="provider_report")
        self.assertTrue(recorded["recorded"])
        report = await self.action("telemetry_report", model="groq")
        self.assertIn("250.0", report)
        with self.assertRaises(WorkbenchError):
            await self.action("telemetry_record", model="groq",
                              latency_ms=-4, input_tokens="",
                              output_tokens="", source="provider_report")
        with self.assertRaises(WorkbenchError):
            await self.action("telemetry_record", model="groq",
                              latency_ms=250, input_tokens="",
                              output_tokens="", energy=2.4,
                              source="provider_report")
        status = await self.action("telemetry_status")
        self.assertIn("no hardware meter", status["energy"])

    async def test_cloud_capture_requires_consent(self):
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("telemetry_capture", model="groq",
                              prompt="ping", allow_cloud=False)
        self.assertIn("consent", str(caught.exception))

    # -- capability 16 -----------------------------------------------------
    async def test_backend_catalog_is_honest_by_default(self):
        described = await self.action("backend_describe")
        states = {entry["engine"]: entry["state"]
                  for entry in described["engines"]}
        self.assertEqual(states["ollama"], "not_configured")
        self.assertEqual(states["vllm-local"], "declared_not_active")
        self.assertIn("refused", described["fallback"])

    async def test_backend_opt_in_requires_hardware_and_owner(self):
        with self.assertRaises(WorkbenchError):
            await self.action("backend_opt_in", engine="sglang-local",
                              approved_by="", measured_ram_gb=32)
        below = await self.action("backend_opt_in", engine="sglang-local",
                                  approved_by="founder", measured_ram_gb=2)
        self.assertEqual(below["state"], "declared_not_active")
        above = await self.action("backend_opt_in", engine="sglang-local",
                                  approved_by="founder", measured_ram_gb=64)
        self.assertEqual(above["state"], "opted_in_not_probed")
        with self.assertRaises(WorkbenchError):
            await self.action("backend_generate", engine="sglang-local",
                              prompt="hi", consented=True)

    async def test_generation_without_configured_engine_is_refused(self):
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("backend_generate", engine="ollama",
                              prompt="hello", consented=True)
        self.assertIn("No configured model", str(caught.exception))
        with self.assertRaises(WorkbenchError):
            await self.action("backend_generate", engine="groq",
                              prompt="hello", consented=False)


if __name__ == "__main__":
    unittest.main()
