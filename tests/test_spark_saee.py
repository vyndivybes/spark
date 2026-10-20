"""SAEE core: advisory discovery plus a project-isolated evolution registry."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_saee import (
    AutonomousEvolutionEngine, SAEEError, KNOWN_CAPABILITIES, KNOWN_GAPS, PIPELINE,
)
from spark_evolution import Evolution, ACTION_KEYS
from spark_maintenance import MaintenanceError
from spark_workspace import SparkWorkspace


class SaeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.temp.name)
        self.saee = AutonomousEvolutionEngine(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_lists_capabilities_gaps_and_pipeline(self):
        registry = self.saee.registry("general")
        ids = {item["id"] for item in registry["capabilities"]}
        self.assertIn("repository_intelligence", ids)
        self.assertIn("source_repair", ids)
        self.assertEqual(registry["pipeline"], list(PIPELINE))
        self.assertFalse(registry["measured"])
        self.assertTrue(all(item["verified"] for item in registry["capabilities"]))
        gap_ids = {item["id"] for item in registry["gaps"]}
        self.assertIn("automatic_deployment", gap_ids)

    def test_discovery_matches_existing_engine_and_is_advisory(self):
        result = self.saee.discover("general", "analyze this local repository and propose an upgrade")
        self.assertFalse(result["executed"])
        self.assertEqual(result["stage"], "plan")
        self.assertTrue(result["matches"])
        self.assertEqual(result["risk"]["level"], "low")
        self.assertTrue(result["plan"])

    def test_discovery_flags_a_real_gap_as_manual(self):
        result = self.saee.discover("general", "organize my windows files and folders automatically")
        self.assertTrue(result["gaps"])
        self.assertEqual(result["risk"]["level"], "high")
        self.assertTrue(any(step["engine"] == "manual" for step in result["plan"]))

    def test_empty_or_oversized_request_is_rejected(self):
        for bad in ("", "   ", "x" * 2001, None, 5):
            with self.assertRaises(SAEEError):
                self.saee.discover("general", bad)

    def test_sync_rejects_bad_project_identifier(self):
        with self.assertRaises(SAEEError):
            self.saee.registry("bad project!")


class SaeLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.temp.name)
        self.saee = AutonomousEvolutionEngine(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_attempt_error_repair_and_benchmark_are_recorded_and_isolated(self):
        self.saee.record_attempt("a", "req1", "test", "candidate staged")
        self.saee.record_error_signature("a", "ImportError: mcp", repair="pip install mcp", verified=True)
        self.saee.record_repair("a", "rep1", "heal_sources", {"status": "applied"})
        self.saee.record_benchmark("a", "startup_ms", 900, 640)
        # A different project sees none of the above.
        self.saee.record_attempt("b", "req2", "plan", "planned")
        ledger_a = self.saee.ledger("a")
        ledger_b = self.saee.ledger("b")
        self.assertEqual(len(ledger_a["attempt"]), 1)
        self.assertEqual(len(ledger_a["error_signature"]), 1)
        self.assertEqual(len(ledger_a["repair"]), 1)
        self.assertEqual(len(ledger_a["benchmark"]), 1)
        self.assertEqual(len(ledger_b["attempt"]), 1)
        self.assertEqual(ledger_b["benchmark"], [])

    def test_benchmark_reports_direction_and_rejects_non_finite(self):
        improved = self.saee.record_benchmark("a", "latency", 120, 80)
        self.assertTrue(improved["improved"])
        self.assertEqual(improved["delta"], -40)
        regressed = self.saee.record_benchmark("a", "latency", 80, 120)
        self.assertFalse(regressed["improved"])
        for bad in (float("nan"), float("inf"), "5", None, True):
            with self.assertRaises(SAEEError):
                self.saee.record_benchmark("a", "latency", bad, 1)

    def test_error_signature_deduplicates(self):
        first = self.saee.record_error_signature("a", "KeyError: missing")
        second = self.saee.record_error_signature("a", "KeyError: missing")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.saee.ledger("a")["error_signature"]), 1)

    def test_failures_lists_only_unverified_signatures(self):
        self.saee.record_error_signature("a", "sig one", verified=True)
        self.saee.record_error_signature("a", "sig two", verified=False)
        failures = self.saee.failures("a")
        self.assertEqual([item["signature"] for item in failures], ["sig two"])

    def test_bad_stage_and_kind_are_rejected(self):
        with self.assertRaises(SAEEError):
            self.saee.record_attempt("a", "req1", "not_a_stage", "x")
        with self.assertRaises(SAEEError):
            self.saee.record_repair("a", "rep1", "", {})

    def test_ledger_is_newest_first_and_bounded(self):
        for index in range(5):
            self.saee.record_attempt("a", "req", "plan", "outcome %d" % index)
        listed = self.saee.ledger("a", limit=2)["attempt"]
        self.assertEqual(len(listed), 2)


class SaeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.temp.name)

        async def generate(instruction, context):
            return {"changes": []}

        self.engine = Evolution(self.workspace, generator=generate)

    async def asyncTearDown(self):
        await self.engine.rea.close()
        self.temp.cleanup()

    async def test_saee_actions_are_exposed_and_dispatch(self):
        for action in ("saee_registry", "saee_discover", "saee_ledger", "saee_failures",
                       "saee_record_attempt", "saee_record_error_signature",
                       "saee_record_benchmark"):
            self.assertIn(action, ACTION_KEYS)
        registry = await self.engine.execute("saee_registry", "general", {})
        self.assertTrue(registry["capabilities"])
        discovered = await self.engine.execute(
            "saee_discover", "general", {"request": "improve repository analysis"})
        self.assertIn("risk", discovered)
        attempt = await self.engine.execute("saee_record_attempt", "general", {
            "request_id": "r1", "stage": "test", "outcome": "ok", "evidence": {}})
        self.assertEqual(attempt["stage"], "test")
        ledger = await self.engine.execute("saee_ledger", "general", {})
        self.assertEqual(len(ledger["attempt"]), 1)

    async def test_invalid_saee_inputs_surface_as_maintenance_error(self):
        with self.assertRaises(MaintenanceError):
            await self.engine.execute("saee_discover", "general", {"request": ""})
        with self.assertRaises(MaintenanceError):
            await self.engine.execute("saee_record_benchmark", "general", {
                "name": "x", "before": float("nan"), "after": 1})


if __name__ == "__main__":
    unittest.main()
