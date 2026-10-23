"""Capabilities 15 & 16 — Telemetry and unified backend self-tests.

Measured-only telemetry (latency/tokens/TTFT honest refusals, energy
refusal), deterministic aggregates/export, and backend catalog behavior:
honest states, cloud consent, optional-engine hardware gating.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_inference_backends import BackendError, InferenceBackends
from spark_inference_telemetry import Telemetry, TelemetryError


def fake_runner(result="a valid generation", tokens=None):
    answer = {"text": result}
    answer.update(tokens or {})
    return answer


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.samples = [{"cpu_percent": 5.0, "ram_used_mb": 4000.0},
                        {"cpu_percent": 40.0, "ram_used_mb": 5200.0}]
        self.telemetry = Telemetry(self.dir.name,
                                   sampler=lambda: self.samples.pop(0))
        self.real_dirs = self.dir

    def test_capture_measures_wall_clock_and_vitals_delta(self):
        def slow_runner():
            total = 0
            for i in range(20000):
                total += i
            return fake_runner()
        entry = self.telemetry.capture("ollama-local:llama3", slow_runner,
                                       measure_again=lambda a: {"input": 10,
                                                                "output": 40})
        self.assertTrue(entry["recorded"])
        aggregate = self.telemetry.aggregate("ollama-local:llama3")[0]
        self.assertGreater(aggregate["latency_p95_ms"], 0)
        self.assertEqual(aggregate["output_tokens_total"], 40)
        self.assertGreater(aggregate["tokens_per_second_mean"], 0)

    def test_ttft_is_honest_and_invented_energy_is_refused(self):
        self.telemetry.record("groq", latency_ms=120,
                              output_tokens=30, source="provider_report")
        with self.assertRaises(TelemetryError):
            self.telemetry.record("groq", latency_ms=120,
                                  ttft_ms=-5, source="provider_report")
        with self.assertRaises(TelemetryError) as caught:
            self.telemetry.record("groq", latency_ms=120, energy=3.2,
                                  source="provider_report")
        self.assertIn("no measured power", str(caught.exception))
        aggregate = self.telemetry.aggregate()[0]
        self.assertIsNone(aggregate["tokens_per_second_mean"])

    def test_bogus_inputs_are_refused(self):
        with self.assertRaises(TelemetryError):
            self.telemetry.record("groq", latency_ms=-1)
        with self.assertRaises(TelemetryError):
            self.telemetry.record("groq", latency_ms=100, output_tokens=0.5)
        with self.assertRaises(TelemetryError):
            self.telemetry.capture("bad model id!", lambda: 1)
        with self.assertRaises(TelemetryError):
            self.telemetry.record("groq", latency_ms=100,
                                  source="self_reported_quality")

    def test_capture_reports_inference_failure_without_fake_numbers(self):
        with self.assertRaises(TelemetryError) as caught:
            self.telemetry.capture("groq", lambda: 1 / 0)
        self.assertIn("nothing measured", str(caught.exception))

    def test_report_is_measured_only_markdown(self):
        self.telemetry.record("groq", latency_ms=150, input_tokens=10,
                              output_tokens=20, source="provider_report")
        report = self.telemetry.report("groq")
        self.assertIn("no estimates are recorded", report.lower())
        self.assertIn("groq", report)
        self.assertIn("150.0", report)

    def test_status_documents_limits(self):
        status = self.telemetry.status()
        self.assertIn("no hardware meter", status["energy"])
        self.assertIn("streamed", status["ttft"])


class BackendsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.telemetry = Telemetry(self.dir.name)
        self.backends = InferenceBackends(self.dir.name, telemetry=self.telemetry)

    def test_describe_honest_states_and_refusals(self):
        described = self.backends.describe()
        by_engine = {entry["engine"]: entry["state"] for entry in
                     described["engines"]}
        self.assertEqual(by_engine["ollama"], "not_configured")
        self.assertEqual(by_engine["vllm-local"], "declared_not_active")
        self.assertIn("refused", described["downloads"])
        self.assertIn("refused", described["fallback"])

    def test_probe_requires_consent_for_cloud_and_records_state(self):
        self.backends.attach("ollama", probe=lambda: {"state": "connected",
                                                      "model": "llama3"})
        self.backends.attach("groq", probe=lambda: {"state": "connected"})
        with self.assertRaises(BackendError):
            self.backends.probe("groq")
        groq = self.backends.probe("groq", consented=True)
        self.assertEqual(groq["state"], "connected")
        self.assertGreaterEqual(groq["latency_ms"], 0)
        events = self.backends.events("groq")
        self.assertEqual(events[0]["kind"], "probe_connected")

    def test_probe_failure_is_measured_and_recorded_as_failed(self):
        def broken():
            raise RuntimeError("no service")
        self.backends.attach("ollama", probe=broken)
        outcome = self.backends.probe("ollama")
        self.assertEqual(outcome["state"], "failed")
        self.assertIn("RuntimeError", outcome["reason"])

    def test_generation_needs_consent_adapter_and_records_telemetry(self):
        self.backends.attach(
            "groq",
            generate=lambda prompt: {"text": "hello world",
                                     "input_tokens": 5, "output_tokens": 7})
        with self.assertRaises(BackendError):
            self.backends.generate("groq", "hi")
        result = self.backends.generate("groq", "hi", consented=True)
        self.assertIn("hello", result["text"])
        aggregate = self.telemetry.aggregate("groq")[0]
        self.assertEqual(aggregate["output_tokens_total"], 7)

    def test_generation_failures_and_invalid_results_are_refused(self):
        self.backends.attach("groq", generate=lambda prompt: {"text": ""})
        with self.assertRaises(BackendError):
            self.backends.generate("groq", "hi", consented=True)
        def broken(prompt):
            raise RuntimeError("boom")
        self.backends.attach("gemini", generate=broken)
        with self.assertRaises(BackendError) as caught:
            self.backends.generate("gemini", "hi", consented=True)
        self.assertIn("RuntimeError", str(caught.exception))

    def test_optional_engine_opt_in_requires_measured_hardware_and_owner(self):
        with self.assertRaises(BackendError):
            self.backends.opt_in_optional("llamacpp-local", approved_by="",
                                          measured_ram_gb=16.0)
        below = self.backends.opt_in_optional("llamacpp-local",
                                              approved_by="founder",
                                              measured_ram_gb=4.0)
        self.assertEqual(below["state"], "declared_not_active")
        opted = self.backends.opt_in_optional("vllm-local",
                                              approved_by="founder",
                                              measured_ram_gb=32.0)
        self.assertEqual(opted["state"], "opted_in_not_probed")
        with self.assertRaises(BackendError):
            self.backends.generate("vllm-local", "hi", consented=True)

    def test_engine_ledger_is_persisted_and_bounded(self):
        self.backends.attach("ollama", probe=lambda: {"state": "connected"})
        for _ in range(3):
            self.backends.probe("ollama")
        self.assertLessEqual(len(self.backends.events("ollama")), 300)
        self.assertEqual(len(self.backends.events("ollama")), 3)


if __name__ == "__main__":
    unittest.main()
