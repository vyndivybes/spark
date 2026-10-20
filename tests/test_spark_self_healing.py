import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_self_healing import (
    RepairGate,
    SelfHealingError,
    check_connectivity,
    check_dependencies,
    check_resources,
    check_runtime,
    check_startup,
    diagnose,
    disk_forecast,
)


class StartupTests(unittest.TestCase):
    def test_real_backend_has_no_startup_failures(self):
        backend = Path(__file__).resolve().parents[1] / "backend"
        result = check_startup(backend)
        self.assertTrue(result["ok"], result["findings"])

    def test_missing_module_is_a_startup_failure(self):
        with self.subTest("empty dir"):
            import tempfile
            with tempfile.TemporaryDirectory() as temp:
                result = check_startup(temp)
                self.assertFalse(result["ok"])
                self.assertTrue(all(f["issue"] == "missing_module" for f in result["findings"]))

    def test_unparseable_module_is_flagged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "spark_maintenance.py").write_text("def (:\n")
            result = check_startup(temp)
            self.assertIn("unparseable", {f["issue"] for f in result["findings"]})


class DependencyTests(unittest.TestCase):
    def test_absent_optional_modules_are_reported_not_installed(self):
        result = check_dependencies(modules=("definitely_absent_module_xyz",))
        self.assertIn("definitely_absent_module_xyz", result["absent"])
        self.assertTrue(result["ok"])


class RuntimeTests(unittest.TestCase):
    def test_runtime_reports_python_and_no_findings(self):
        result = check_runtime()
        self.assertTrue(result["ok"])
        self.assertIn(".", result["python"])


class ResourceTests(unittest.TestCase):
    def test_injected_vitals_trigger_low_floors(self):
        result = check_resources(vitals={"ram_available_gb": 0.1, "disk_free_gb": 0.2},
                                 ram_floor_gb=0.5, disk_floor_gb=1.0)
        self.assertFalse(result["ok"])
        self.assertEqual({f["resource"] for f in result["findings"]}, {"ram", "disk"})

    def test_healthy_headroom_passes(self):
        result = check_resources(vitals={"ram_available_gb": 4.0, "disk_free_gb": 50.0})
        self.assertTrue(result["ok"])


class ConnectivityTests(unittest.TestCase):
    def test_no_probe_is_opt_in(self):
        result = check_connectivity()
        self.assertIsNone(result["ok"])
        self.assertEqual(result["checked"], [])

    def test_injected_probe_never_hits_network(self):
        calls = []

        def probe(host, port):
            calls.append((host, port))
            return host == "github.com"

        result = check_connectivity(probe=probe)
        self.assertFalse(result["ok"])
        self.assertTrue(calls)


class DiagnoseTests(unittest.TestCase):
    def test_diagnose_is_read_only_and_healthy(self):
        result = diagnose()
        self.assertIn("startup", result)
        self.assertIn("dependencies", result)
        self.assertIn("connectivity", result)
        self.assertIsNone(result["connectivity"]["ok"])

    def test_deep_without_probe_still_does_not_connect(self):
        # deep=True enables probing only when a probe function is supplied.
        result = diagnose(deep=True)
        self.assertIsNone(result["connectivity"]["ok"])


class RepairGateTests(unittest.TestCase):
    def test_identical_retry_is_refused(self):
        gate = RepairGate()
        self.assertTrue(gate.allow("sig", {"error": "x"})["allowed"])
        self.assertFalse(gate.allow("sig", {"error": "x"})["allowed"])

    def test_new_evidence_allows_retry(self):
        gate = RepairGate()
        gate.allow("sig", {"error": "x"})
        self.assertEqual(gate.allow("sig", {"error": "y"})["reason"], "new_attempt")

    def test_seeded_attempts_are_honoured(self):
        gate = RepairGate(attempts=[{"signature": "sig", "evidence": RepairGate._evidence_digest({"e": 1})}])
        self.assertFalse(gate.allow("sig", {"e": 1})["allowed"])

    def test_repeated_failures_surface(self):
        gate = RepairGate()
        gate.allow("a", {"1": 1})
        gate.allow("a", {"2": 2})
        gate.allow("b", {"1": 1})
        self.assertEqual(gate.repeated_failures(), ["a"])

    def test_empty_signature_rejected(self):
        with self.assertRaises(SelfHealingError):
            RepairGate().allow("")


class DiskForecastTests(unittest.TestCase):
    def test_projection_warns_when_it_will_empty(self):
        result = disk_forecast(10.0, 0.5, horizon_days=30)
        self.assertTrue(result["warning"])
        self.assertEqual(result["days_to_empty"], 20.0)

    def test_stable_disk_does_not_warn(self):
        result = disk_forecast(100.0, 0.0, horizon_days=30)
        self.assertFalse(result["warning"])
        self.assertIsNone(result["days_to_empty"])

    def test_non_numeric_rejected(self):
        with self.assertRaises(SelfHealingError):
            disk_forecast("x", 1, horizon_days=1)


if __name__ == "__main__":
    unittest.main()
