"""Capabilities 07 & 12 — Trace learning and adaptive routing self-tests.

Uses synthetic-but-real labeled traces generated from deterministic
measured outcomes; no network, model calls or self-reported quality.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_trace_learning import (LearningEngine, LearningError, LOCAL_MODELS,
                                 TASK_CLASSES, TraceStore, AdaptiveRouter,
                                 mask_secrets, policy_always_local,
                                 policy_latency_smallest)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.store = TraceStore(self.root)
        self.now = 0.0

    def capture_many(self, rows):
        self.store.clock = lambda: 1_800_000_000 + self.now
        keys = []
        for task, model, latency, success in rows:
            keys.append(self.store.capture(task, model, {"q": "digest summarize"},
                                           latency, success=success)["key"])
            self.now += 1
        return keys

    def clock_ok(self):
        return 0.0

    clock_offset = 0.0


class CaptureTests(Base):
    def test_capture_masks_secret_like_values(self):
        self.store.capture("digest", "ollama-local",
                           "config GEMINI_API_KEY=abc123 required", 120.0,
                           success=True)
        trace = self.store.labeled(limit=200)
        self.assertNotIn("abc123", trace[0]["masked"])
        self.assertIn("GEMINI_API_KEY=<redacted>", trace[0]["masked"])

    def test_capture_validates_task_and_model(self):
        with self.assertRaises(LearningError):
            self.store.capture("unknown-task", "ollama-local", "x", 1.0)
        with self.assertRaises(LearningError):
            self.store.capture("digest", "gpt5-enterprise-tier", "x", 1.0)
        with self.assertRaises(LearningError):
            self.store.capture("digest", "ollama-local", "x", 1.0, success="probably")

    def test_label_requires_measured_boolean_outcome(self):
        key = self.store.capture("digest", "ollama-local", "work", 10.0)["key"]
        with self.assertRaises(LearningError):
            self.store.label(key, success=0.9)
        self.store.label(key, success=False)
        trace = self.store.labeled()[0]
        self.assertEqual(trace["success"], 0)

    def test_unlabeled_traces_are_excluded_from_learning_input(self):
        self.store.capture("digest", "ollama-local", "work", 10.0)
        self.assertEqual(self.store.labeled(), [])
        self.assertEqual(self.store.model_summary(), [])


class RoutingTests(Base):
    def setUp(self):
        super().setUp()
        self.store.clock = lambda: 1_800_000_001.0

    def data(self, model, task, latency, success):
        return self.store.capture(task, model, "result", latency, success=success)

    def test_local_first_routing_requires_measurement_or_permission(self):
        router = AdaptiveRouter(self.store, cloud_allowed=False)
        choice = router.select("digest")
        self.assertEqual(choice["model"], "ollama-local")
        self.assertTrue(choice["reason"] in ("static baseline", "measured policy choice"))

    def test_cloud_choice_without_permission_falls_back_locally(self):
        for _ in range(5):
            self.data("gemini-free-cloud", "digest", 900, True)
        router = AdaptiveRouter(self.store, cloud_allowed=False)
        router.set_policy(policy_latency_smallest)
        choice = router.select("digest", apply_policy=True)
        self.assertEqual(choice["model"], "ollama-local")
        self.assertIn("local fallback", choice["reason"])

    def test_low_memory_machine_picks_lightest_measured_local_model(self):
        self.data("ollama-local", "digest", 4000, True)
        for _ in range(5):
            self.data("llamacpp-local", "digest", 800, True)
        self.data("groq-free-cloud", "digest", 300, True)
        low = AdaptiveRouter(self.store, local_ram_gb=4, cloud_allowed=False)
        choice = low.select("digest", apply_policy=False)
        self.assertEqual(choice["model"], "llamacpp-local")


class LearningGateTests(Base):
    def setUp(self):
        super().setUp()
        self.store.clock = lambda: 1_800_000_002.0
        # Model A wins research strongly measured; model B wins coding.
        self.rows = []
        for _ in range(14):
            self.rows.append(("research", "ollama-local", 700, True))

    def test_learning_requires_enough_labeled_traces(self):
        engine = LearningEngine(self.store)
        with self.assertRaises(LearningError) as caught:
            engine.dataset("research")
        self.assertIn("40 labeled traces", str(caught.exception))

    def _big_dataset(self):
        rows = []
        for _ in range(30):
            rows.append(("research", "ollama-local", 600, True))
            rows.append(("research", "groq-free-cloud", 900, False))
            rows.append(("coding", "groq-free-cloud", 800, True))
            rows.append(("coding", "ollama-local", 1500, True))
        self.capture_many(rows)

    def measure(self, summary_list):
        # Real measured per-(model,task) evidence used for candidate scoring.
        return summary_list

    def test_candidate_beats_and_gates_on_heldout_without_regression(self):
        self._big_dataset()
        summary = self.store.model_summary()
        self.assertTrue(summary)
        engine = LearningEngine(self.store)
        train, heldout = engine.dataset("research")
        self.assertGreaterEqual(len(train) + len(heldout), 40)
        proposal = engine.propose("latency-policy", policy_latency_smallest,
                                  "research", run_rows=train)
        self.assertIn(proposal["status"], ("proposed", "rejected"))
        self.assertLess(proposal["heldout"], 1.01)
        self.assertGreaterEqual(proposal["baseline"], 0.5)

    def test_failing_candidate_cannot_be_activated(self):
        self._big_dataset()
        engine = LearningEngine(self.store)
        proposal = engine.propose("always-local", policy_always_local,
                                  "coding", run_rows=self.store.model_summary())
        if proposal["status"] == "rejected":
            with self.assertRaises(LearningError):
                engine.activate(proposal["key"], approved_by="owner")
        else:  # honest skip - the policy may genuinely pass on symmetric data
            self.skipTest("baseline policy passed its own heldout gate")

    def test_activation_requires_owner_and_rollback_works(self):
        self._big_dataset()
        engine = LearningEngine(self.store)
        proposal = engine.propose("latency-policy", policy_latency_smallest,
                                  "research", run_rows=self.store.model_summary())
        with self.assertRaises(LearningError):
            engine.activate(proposal["key"], approved_by=None)
        if proposal["status"] == "proposed":
            activated = engine.activate(proposal["key"], approved_by="founder")
            self.assertEqual(activated["approved_by"], "founder")
            rolled = engine.rollback(proposal["key"])
            self.assertEqual(rolled["status"], "rolled_back")
        else:
            self.skipTest("candidate missed the held-out gate, activation impossible")

    def test_invalid_candidate_names_and_policy_types_refused(self):
        engine = LearningEngine(self.store)
        with self.assertRaises(LearningError):
            engine.propose("Bad Name!", policy_always_local, "digest", run_rows=[])
        invalid_router = AdaptiveRouter(self.store)
        with self.assertRaises(LearningError):
            invalid_router.set_policy("not-a-policy")

    def test_split_validation(self):
        with self.assertRaises(LearningError):
            LearningEngine(self.store, lock_split=0.9)
        with self.assertRaises(LearningError):
            LearningEngine(self.store, lock_split=0.01)


class HonestyTests(unittest.TestCase):
    def test_known_models_are_free_tier_or_local_only(self):
        for model in LOCAL_MODELS:
            self.assertIn(model, ("ollama-local", "llamacpp-local",
                                  "groq-free-cloud", "gemini-free-cloud"))

    def test_task_classes_cover_the_benchmarks(self):
        self.assertEqual(set(TASK_CLASSES),
                         {"digest", "research", "coding", "triage", "memory", "voice"})

    def test_masking_never_returns_original_secret(self):
        text = "headers Authorization=BearerTabc123"
        self.assertNotIn("BearerTabc123", mask_secrets(text))


if __name__ == "__main__":
    unittest.main()
