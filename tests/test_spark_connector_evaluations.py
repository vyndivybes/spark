"""Capabilities 13 & 14 — Connector catalog and standardized evaluations.

Connector lifecycle: disabled -> configured (owner consent) -> account
validated -> verified read with cursor + freshness + failure + revoke.
Evaluations: seven suites, deterministic scoring, honest provenance,
markdown report export. Fully offline with injected adapters/runners.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_connector_catalog import ConnectorCatalog, ConnectorError
from spark_evaluations import EvaluationError, Evaluations


class CatalogBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock_value = [1_800_000_000.0]
        self.catalog = ConnectorCatalog(self.dir.name,
                                        clock=lambda: self.clock_value[0])
        self.reads = []

    def advance(self, seconds=10.0):
        self.clock_value[0] += seconds

    def attach(self):
        def validate():
            return "owner@example-account"
        def read_page(cursor, limit):
            self.reads.append((cursor, limit))
            return {"items": ["item-1", "item-2"], "cursor": "next-page-2",
                    "source_time": self.clock_value[0]}
        def revoke():
            self.revoked = True
        self.revoked = False
        self.catalog.register("gmail.snapshot", "Google", scope="read-only mail "
                              "headers for the digest",
                              validate_account=validate,
                              read_page=read_page, revoke=revoke)
        return self.catalog


class CatalogLifecycleTests(CatalogBase):
    def test_new_connectors_import_disabled_and_race_no_state(self):
        catalog = self.attach()
        state = catalog.state("gmail.snapshot")
        self.assertEqual(state["state"], "disabled")
        with self.assertRaises(ConnectorError):
            catalog.read_page("gmail.snapshot")

    def test_configure_needs_consent_and_reads_need_validation(self):
        catalog = self.attach()
        with self.assertRaises(ConnectorError):
            catalog.configure("gmail.snapshot", "owner@example-account",
                              consented=False)
        configure = catalog.configure("gmail.snapshot", "owner@example-account",
                                      consented=True)
        self.assertEqual(configure["state"], "configured")
        with self.assertRaises(ConnectorError):
            catalog.read_page("gmail.snapshot")

    def test_account_validation_failure_is_recorded_and_fails_the_connector(self):
        catalog = self.attach()
        catalog.adapters["gmail.snapshot"]["validate_account"] = (
            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        catalog.configure("gmail.snapshot", "owner@example-account",
                          consented=True)
        with self.assertRaises(ConnectorError) as caught:
            catalog.validate_account("gmail.snapshot")
        self.assertIn("RuntimeError", str(caught.exception))
        self.assertEqual(catalog.state("gmail.snapshot")["state"], "failed")

    def test_verified_read_captures_cursor_timestamp_and_rate_limit(self):
        catalog = self.attach()
        catalog.configure("gmail.snapshot", "owner@example-account",
                          consented=True)
        state = catalog.validate_account("gmail.snapshot")
        self.assertEqual(state["state"], "account_validated")
        read = catalog.read_page("gmail.snapshot")
        self.assertEqual(read["state"], "verified_read")
        self.assertEqual(len(read["items"]), 2)
        self.assertEqual(self.reads[0], (None, 20))
        with self.assertRaises(ConnectorError) as caught:
            catalog.read_page("gmail.snapshot")
        self.assertIn("Rate limit", str(caught.exception))
        self.advance(20)
        second = catalog.read_page("gmail.snapshot")
        self.assertEqual(self.reads[1][0], "next-page-2")

    def test_freshness_marks_stale_and_failure_state_is_judged(self):
        catalog = self.attach()
        catalog.configure("gmail.snapshot", "owner@example-account",
                          consented=True)
        catalog.validate_account("gmail.snapshot")
        catalog.read_page("gmail.snapshot")
        fresh = catalog.freshness("gmail.snapshot", stale_after_seconds=60)
        self.assertEqual(fresh["freshness"], "fresh")
        self.advance(90)
        stale = catalog.freshness("gmail.snapshot", stale_after_seconds=60)
        self.assertEqual(stale["freshness"], "stale")
        self.assertEqual(stale["state"], "stale")

    def test_revoke_requires_owner_and_clears_identity(self):
        catalog = self.attach()
        catalog.configure("gmail.snapshot", "owner@example-account",
                          consented=True)
        catalog.validate_account("gmail.snapshot")
        with self.assertRaises(ConnectorError):
            catalog.revoke("gmail.snapshot", approved_by="")
        revoked = catalog.revoke("gmail.snapshot", approved_by="founder")
        self.assertTrue(self.revoked)
        self.assertEqual(revoked["state"], "revoked")
        self.assertEqual(revoked["account"], "")
        with self.assertRaises(ConnectorError):
            catalog.configure("gmail.snapshot", "owner@example-account",
                              consented=True)
        self.advance(1)
        events = catalog.events("gmail.snapshot")
        kinds = [event["kind"] for event in events]
        self.assertIn("revoked", kinds)

    def test_missing_adapters_and_registration_bounds_are_refused(self):
        catalog = self.attach()
        with self.assertRaises(ConnectorError):
            catalog.register("email-bare", "Mail", scope="console")
        with self.assertRaises(ConnectorError):
            catalog.register("Bad ID", "Mail", scope="read")
        for i in range(15):
            catalog.register("local.source-%d" % i, "Local", scope="local",
                             read_page=lambda c, l: {"items": []})
        with self.assertRaises(ConnectorError):
            catalog.register("local.source-16", "Local", scope="local",
                             read_page=lambda c, l: {"items": []})


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.evaluations = Evaluations(self.dir.name)

    def good_runner(self, case):
        suite_target = case["id"].split("-", 1)[0]
        if case["id"] == "triage-never-assert-thread-unseen":
            return {"classification": "archive"}
        if suite_target == "triage":
            option = {"triage-reply-required": "reply_required",
                      "triage-calendar-event": "calendar"}.get(case["id"])
            return {"classification": option or "archive"}
        if suite_target == "meeting":
            if case["id"] in ("meeting-conflict", "meeting-shift-proposal"):
                return "conflict"
            return "free"
        if suite_target == "citations":
            return {"sources": ["src1"], "stop": None}
        if case["id"] == "unverified-stops":
            return {"stop": "no_evidence"}
        if case["id"] == "contradiction-flagged":
            return {"sources": ["a", "b"], "contradiction": "conflict"}
        if suite_target == "code":
            if case["id"] == "code-destructive-refused":
                return "refused"
            if case["id"] == "code-bounded-edit-with-tests":
                return ["applied", "tests_recorded"]
            return "not_activated"
        if suite_target == "policy":
            if case["id"] == "policy-side-effect-denied":
                return "refused"
            if case["id"] == "policy-side-effect-allowed-with-grant":
                return ["applied", "requires_owner_log"]
            return "applied"
        if suite_target == "memory":
            return case["input"]["memory"] or "not_stored"
        if case["id"] == "repair-no-tests-no-apply":
            return "not_activated"
        return ["staged", "tests_passed"]

    def bad_runner(self, case):
        return "wrong"

    def candidate(self, runner, name="gold-standard"):
        self.evaluations.register(name, runner,
                                  provenance="fixture reference candidate")
        return name

    def test_all_seven_suites_exist_and_are_labeled(self):
        for suite in ("email_triage", "meeting_inference", "research_citations",
                      "safe_code_modification", "agent_tool_policy",
                      "memory_retrieval", "self_repair"):
            cases = self.evaluations.suites(suite)
            self.assertGreaterEqual(len(cases), 2)
            self.assertTrue(all("expected" in case and "id" in case
                                for case in cases))

    def test_reference_candidate_scores_perfectly_and_fails_loudly_otherwise(self):
        gold = self.candidate(self.good_runner)
        for suite in self.evaluations.status()["suites"]:
            run = self.evaluations.run(gold, suite)
            self.assertEqual(run["pass_rate"], 1.0, suite)
            self.assertEqual(run["failures"], [])
        broken = self.candidate(self.bad_runner, name="fail-always")
        run = self.evaluations.run(broken, "email_triage")
        self.assertEqual(run["passed"], 0)
        self.assertEqual(len(run["failures"]), run["total"])

    def test_unregistered_candidate_and_unknown_suite_are_refused(self):
        with self.assertRaises(EvaluationError):
            self.evaluations.run("ghost", "email_triage")
        self.candidate(self.good_runner)
        with self.assertRaises(EvaluationError):
            self.evaluations.run("gold-standard", "not-a-suite")

    def test_reports_are_reproducible_with_provenance_and_exportable(self):
        gold = self.candidate(self.good_runner)
        broken = self.candidate(self.bad_runner, name="fail-always")
        first = self.evaluations.run(gold, "email_triage")
        second = self.evaluations.run(gold, "email_triage")
        self.assertEqual(first["passed"], second["passed"])
        self.assertEqual(self.evaluations.run(broken, "self_repair")["passed"], 0)
        report = self.evaluations.report(broken, "self_repair")
        self.assertIn("pass rate: 0%", report)
        self.assertIn("fixture:", report)
        self.assertIn("not a live model claim", report)
        exported = self.evaluations.export(broken, "self_repair", self.dir.name)
        self.assertTrue(Path(exported["exported"]).exists())

    def test_history_and_status_honest(self):
        gold = self.candidate(self.good_runner)
        before = self.evaluations.status()["runs_recorded"]
        self.evaluations.run(gold, "memory_retrieval")
        self.assertEqual(self.evaluations.status()["runs_recorded"], before + 1)
        self.assertEqual(self.evaluations.history()[0]["suite"],
                         "memory_retrieval")


if __name__ == "__main__":
    unittest.main()
