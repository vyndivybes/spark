import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_profiler import (
    FRONTEND_SECTIONS,
    ProfilerError,
    ProfileRecorder,
    compare,
    frontend_probe,
    import_cost,
    profile_callable,
    resource_delta,
)


class RecorderTests(unittest.TestCase):
    def test_summary_reports_distribution(self):
        recorder = ProfileRecorder()
        for value in (0.1, 0.2, 0.3, 0.4, 0.5):
            recorder.record("op", value)
        summary = recorder.summary("op")
        self.assertEqual(summary["count"], 5)
        self.assertEqual(summary["min"], 0.1)
        self.assertEqual(summary["max"], 0.5)
        self.assertLessEqual(summary["p50"], summary["p95"])

    def test_unknown_name_is_empty(self):
        self.assertEqual(ProfileRecorder().summary("x")["count"], 0)

    def test_measure_uses_injected_clock(self):
        ticks = iter([1.0, 1.25])
        recorder = ProfileRecorder(clock=lambda: next(ticks))
        with recorder.measure("block"):
            pass
        self.assertAlmostEqual(recorder.summary("block")["mean"], 0.25)

    def test_rejects_bad_values(self):
        recorder = ProfileRecorder()
        for bad in (-1, float("nan"), float("inf"), "x", True):
            with self.subTest(bad=bad):
                with self.assertRaises(ProfilerError):
                    recorder.record("op", bad)

    def test_rejects_empty_name(self):
        with self.assertRaises(ProfilerError):
            ProfileRecorder().record("", 1.0)


class CompareTests(unittest.TestCase):
    def test_clear_improvement(self):
        self.assertEqual(compare("t", 1.0, 0.5)["verdict"], "improved")

    def test_clear_regression(self):
        self.assertEqual(compare("t", 1.0, 1.5)["verdict"], "regressed")

    def test_noise_is_not_an_improvement(self):
        result = compare("t", 1.0, 1.03, tolerance=0.10)
        self.assertEqual(result["verdict"], "no_measurable_change")
        self.assertIn("noise", result["recommendation"].lower())

    def test_higher_is_better_inverts(self):
        self.assertEqual(compare("throughput", 1.0, 2.0, lower_is_better=False)["verdict"], "improved")

    def test_zero_baseline_handled(self):
        self.assertEqual(compare("t", 0.0, 0.0)["verdict"], "no_measurable_change")
        self.assertEqual(compare("t", 0.0, 1.0)["verdict"], "regressed")

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ProfilerError):
            compare("t", 1.0, float("nan"))
        with self.assertRaises(ProfilerError):
            compare("t", 1.0, 2.0, tolerance=5)
        with self.assertRaises(ProfilerError):
            compare("t", "x", 2.0)


class ImportCostTests(unittest.TestCase):
    def test_measures_a_stdlib_import(self):
        result = import_cost("sys")
        self.assertEqual(result["module"], "sys")
        self.assertGreaterEqual(result["seconds"], 0.0)
        self.assertEqual(result["repeats"], 1)

    def test_missing_module_raises(self):
        with self.assertRaises(ProfilerError):
            import_cost("definitely_absent_module_xyz")

    def test_invalid_module_name_rejected(self):
        for bad in ("", "os;rm", "1bad"):
            with self.subTest(bad=bad):
                with self.assertRaises(ProfilerError):
                    import_cost(bad)

    def test_bad_repeats_rejected(self):
        with self.assertRaises(ProfilerError):
            import_cost("sys", repeats=0)


class ResourceDeltaTests(unittest.TestCase):
    def test_reports_growth_and_findings(self):
        result = resource_delta({"ram_available_gb": 2.0, "disk_free_gb": 10.0},
                                {"ram_available_gb": 1.0, "disk_free_gb": 10.0})
        self.assertEqual(result["deltas"]["ram_available_gb"], -1.0)
        self.assertEqual(result["findings"][0]["resource"], "ram")

    def test_only_shared_keys_compared(self):
        result = resource_delta({"ram_available_gb": 2.0}, {"disk_free_gb": 5.0})
        self.assertEqual(result["deltas"], {})

    def test_rejects_non_mapping(self):
        with self.assertRaises(ProfilerError):
            resource_delta([], {})


class ProfileCallableTests(unittest.TestCase):
    def test_records_each_run(self):
        recorder = profile_callable(lambda: sum(range(100)), name="s", repeats=4)
        self.assertEqual(recorder.summary("s")["count"], 4)

    def test_rejects_non_callable(self):
        with self.assertRaises(ProfilerError):
            profile_callable(5)

    def test_rejects_bad_repeats(self):
        with self.assertRaises(ProfilerError):
            profile_callable(lambda: None, repeats=0)


class FrontendProbeTests(unittest.TestCase):
    def runner(self, text):
        return lambda root, section, repeats: text

    def test_summarises_timings_with_context(self):
        report = frontend_probe("SparkScreens", 3, runner=self.runner(
            "[200.04, 180.01, 260.0]"))
        self.assertEqual(report["section"], "SparkScreens")
        self.assertEqual(report["timings_ms"], [180.0, 200.0, 260.0])
        self.assertEqual(report["mean_ms"], 213.3)
        self.assertGreaterEqual(report["p95_ms"], report["mean_ms"])
        self.assertIn("offline", report["context"])
        self.assertIn("react-dom/server", report["context"])

    def test_unknown_section_rejected(self):
        with self.assertRaises(ProfilerError):
            frontend_probe("NotAShippedScreen", 1, runner=self.runner([1.0]))
        self.assertEqual(FRONTEND_SECTIONS, ("SparkScreens", "IntelligenceConsole"))

    def test_repeats_bounds_enforced(self):
        with self.assertRaises(ProfilerError):
            frontend_probe("SparkScreens", 0, runner=self.runner([]))
        with self.assertRaises(ProfilerError):
            frontend_probe("SparkScreens", 11, runner=self.runner([]))

    def test_count_mismatch_and_junk_rejected(self):
        with self.assertRaises(ProfilerError):
            frontend_probe("SparkScreens", 2, runner=self.runner(
                "[1.0, 2.0, 3.0]"))
        with self.assertRaises(ProfilerError):
            frontend_probe("SparkScreens", 1, runner=self.runner("<html>"))
        with self.assertRaises(ProfilerError):
            frontend_probe("SparkScreens", 1, runner=self.runner("[9999999.0]"))
        with self.assertRaises(ProfilerError):
            frontend_probe("SparkScreens", 2, runner=self.runner("[1.0]"))

    def test_dispatch_arm_and_validation(self):
        import asyncio
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
        try:
            from test_helpers import temp_workspace
            workspace, cleanup = temp_workspace()
        except ModuleNotFoundError:
            from spark_workspace import SparkWorkspace
            import tempfile
            handle = tempfile.TemporaryDirectory()
            workspace, cleanup = SparkWorkspace(handle.name), handle.cleanup
        try:
            from spark_evolution import Evolution, ACTION_KEYS, MaintenanceError
            self.assertEqual(ACTION_KEYS["profile_frontend"], {"section", "repeats"})
            engine = Evolution(
                workspace,
                generator=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model")))
            with self.assertRaises(MaintenanceError):
                asyncio.run(engine.execute(
                    "profile_frontend", "general", {"section": "X", "repeats": 1}))
            report = asyncio.run(engine.execute(
                "profile_frontend", "general", {"section": "SparkScreens", "repeats": 1}))
            self.assertEqual(report["repeats"], 1)
            self.assertIn("context", report)
        finally:
            cleanup()


if __name__ == "__main__":
    unittest.main()
