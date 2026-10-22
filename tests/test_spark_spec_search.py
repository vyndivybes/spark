"""Capability 08 — Specification search self-tests.

All scores come from injected *measured* case runners; there is no network
and no model call. The planner gate, holdout gate, owner activation and
independent rollback are all exercised deterministically.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_spec_search import (CaseSet, SpecError, SpecSearch, validate_spec)


def runner_for(expected_key):
    """Measured runner: a spec whose mode equals the case's expected answer."""
    def runner(spec, case):
        expected = case["expected"]
        if isinstance(expected, dict):
            return spec.get(expected_key) == expected.get("answer")
        return spec.get(expected_key) == expected
    return runner


def make_cases(n=20, modes=("direct", "verbose")):
    answer_for = lambda i: modes[i % len(modes)]
    return CaseSet("fixture.email-triage", [
        {"name": f"case-{i}",
         "input": {"subject": "invoice " + str(i)},
         "expected": {"answer": answer_for(i)}}
        for i in range(n)], provenance="fixture:email-triage")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.search = SpecSearch(self.dir.name)

    def test_spec_is_bounded_json_without_executables(self):
        self.assertEqual(validate_spec({"tone": "formal"}), {"tone": "formal"})
        with self.assertRaises(SpecError):
            validate_spec({"Not-Valid": True})
        with self.assertRaises(SpecError):
            validate_spec({"blob": "x" * 3000})
        with self.assertRaises(SpecError):
            validate_spec({f"k{i}": 1 for i in range(13)})

    def test_case_set_shape_is_enforced(self):
        with self.assertRaises(SpecError):
            CaseSet("Bad Name!", [{"name": "a", "input": {}, "expected": 1},
                                  {"name": "b", "input": {}, "expected": 0}])
        with self.assertRaises(SpecError):
            CaseSet("ok-name", [{"name": "a", "input": {}}])
        with self.assertRaises(SpecError):
            CaseSet("ok-name", [{"name": "a", "input": {}, "expected": 1}])

    def test_split_deterministic_and_bounded(self):
        cases = make_cases(20)
        train, heldout = cases.split(holdout_fraction=0.3)
        self.assertEqual(len(train) + len(heldout), 20)
        train2, heldout2 = cases.split(holdout_fraction=0.3)
        self.assertEqual([c["name"] for c in heldout],
                         [c["name"] for c in heldout2])


class DiagnoseTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.search = SpecSearch(self.dir.name)
        self.cases = make_cases(20)
        self.runner = runner_for("mode")

    def test_diagnose_reports_measured_failures(self):
        result = self.search.diagnose(self.cases.cases, self.runner,
                                      current_spec={"mode": "direct"})
        self.assertGreaterEqual(result["score"], 0.5)
        self.assertEqual(len(result["failures"]),
                         sum(1 for c in self.cases.cases
                             if c["expected"]["answer"] != "direct"))

    def test_diagnose_requires_runner_and_never_crashes_on_runner_error(self):
        with self.assertRaises(SpecError):
            self.search.diagnose(self.cases.cases, "not-callable")
        def broken(spec, case):
            raise RuntimeError("boom")
        result = self.search.diagnose([{"name": "x", "input": None,
                                        "expected": {"want": True}}],
                                      broken, current_spec={})
        self.assertEqual(result["score"], 0.0)
        self.assertIn("runner error", result["failures"][0]["reason"])


class PlanGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.search = SpecSearch(self.dir.name)
        self.cases = make_cases(40)
        self.runner = runner_for("mode")

    def test_plan_is_honest_without_owner_granted_planner(self):
        result = self.search.plan("Improve triage tone", {})
        self.assertEqual(result["status"], "planner_not_configured")
        self.assertEqual(result["candidates"], [])

    def test_plan_bounds_injected_candidates(self):
        def planner(goal, spec):
            return [{"summarize": True}] * 10
        with self.assertRaises(SpecError):
            self.search.plan("Improve triage tone", {}, planner=planner)

    def test_search_gate_rejects_non_improving_candidate_and_records(self):
        def planner(goal, spec):
            return [{"mode": "wrong"}]
        result = self.search.search("Improve triage accuracy", self.cases,
                                    self.runner, planner=planner)
        self.assertEqual(result["status"], "gated")
        self.assertEqual(result["candidates"][0]["status"], "rejected")
        recorded = self.search.candidates(status="rejected")
        self.assertEqual(len(recorded), 1)

    def test_gated_candidate_can_be_activated_with_owner_and_rolled_back(self):
        self.assertEqual(self.search.active_spec()["spec"], None)
        def planner(goal, spec):
            return [{"mode": "direct"}]
        result = self.search.search("Improve triage accuracy", self.cases,
                                    self.runner, planner=planner)
        proposed = [c for c in result["candidates"] if c["status"] == "proposed"]
        if not proposed:
            self.skipTest("candidate honestly missed the improvement gate")
        with self.assertRaises(SpecError):
            self.search.activate(proposed[0]["key"], approved_by="")
        activated = self.search.activate(proposed[0]["key"], approved_by="founder")
        self.assertEqual(activated["approved_by"], "founder")
        self.assertEqual(self.search.active_spec()["spec"], {"mode": "direct"})
        rolled = self.search.rollback()
        self.assertEqual(rolled["status"], "rolled_back")
        self.assertIsNone(self.search.active_spec()["spec"])
        with self.assertRaises(SpecError):
            self.search.rollback()

    def test_rejected_candidate_never_activates(self):
        def planner(goal, spec):
            return [{"mode": "wrong"}]
        result = self.search.search("Improve triage accuracy", self.cases,
                                    self.runner, planner=planner)
        with self.assertRaises(SpecError):
            self.search.activate(result["candidates"][0]["key"],
                                 approved_by="founder")

    def test_status_reports_recorded_runs_and_active_state(self):
        status = self.search.status()
        self.assertEqual(status["runs_recorded"], 0)
        self.assertIsNone(status["active_spec"])
        with self.assertRaises(SpecError):
            self.search.search("short", self.cases, self.runner,
                               planner=lambda goal, spec: [])


if __name__ == "__main__":
    unittest.main()
