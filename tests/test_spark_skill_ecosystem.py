"""Capability 09 — Skill ecosystem self-tests.

Manifest validation, license/checksum gates, owner-bound tool grants,
bounded pipeline invocation (including grant refusals and failure
recording), and independent revoke/rollback. Fully offline.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_skill_ecosystem import SkillEcosystem, SkillEcosystemError


def manifest(instructions="# harmless", **overrides):
    fields = {"name": "digest-helper",
              "description": "Summarize a digest snapshot locally.",
              "license": "MIT",
              "provenance": "https://example.org/skills/digest-helper",
              "sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
              "instructions": instructions,
              "requested_tools": ["text.summary"]}
    fields.update(overrides)
    return fields


class EcosystemBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.eco = SkillEcosystem(self.dir.name)
        self.now = [1_800_000_000.0]
        self.eco.clock = lambda: self.now[0]
        self.eco.register_operation("text.summary",
                                    lambda ctx, prior: "summary:" + str(ctx)[:8])
        self.eco.register_operation("search.obsidian",
                                    lambda ctx, prior: ["note"])

    def advance(self):
        self.now[0] += 5
        return self.now[0]


class ImportTests(EcosystemBase):
    def test_valid_import_is_reviewable_with_integrity_evidence(self):
        result = self.eco.import_skill(manifest(), provided_by="founder")
        self.assertEqual(result["status"], "imported.unreviewed")
        self.assertEqual(result["integrity"], "verified_digest_only")
        self.assertIn("owner review", result["note"])

    def test_undisclosed_license_and_bad_checksum_are_refused(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(manifest(license="Proprietary-EULA"),
                                  provided_by="x")
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(manifest(sha256="0" * 64), provided_by="x")

    def test_executable_code_blocks_are_refused(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(
                manifest(instructions="run:\n```bash\nrm -rf /\n```"),
                provided_by="x")
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(
                manifest(instructions="step\n```python\nimport os\n```"),
                provided_by="x")

    def test_provenance_and_fields_are_bounded(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(manifest(provenance="ftp://host/skill"),
                                  provided_by="x")
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(manifest(requested_tools=["Bad Tool!"]),
                                  provided_by="x")
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(manifest(description=""), provided_by="x")


class ReviewGrantTests(EcosystemBase):
    def setUp(self):
        super().setUp()
        self.imported = self.eco.import_skill(manifest(), provided_by="founder")
        self.key = self.imported["key"]

    def test_review_requires_owner_and_registered_operations(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.review(self.key, approved_by="", granted_tools=["text.summary"])
        with self.assertRaises(SkillEcosystemError):
            self.eco.review(self.key, approved_by="founder",
                            granted_tools=["never.registered"])
        reviewed = self.eco.review(self.key, approved_by="founder",
                                   granted_tools=["text.summary"])
        self.assertEqual(reviewed["granted_tools"], ["text.summary"])
        self.assertTrue(reviewed["instruction_only"])

    def test_review_refuses_unknown_requested_tools_but_records_them(self):
        self.eco.clock = lambda: self.now[0]
        imported = self.eco.import_skill(
            manifest(instructions="plain text",
                     requested_tools=["text.summary", "shell.exec"]),
            provided_by="founder")
        # shell.exec is not registered: grants cannot invent it.
        reviewed = self.eco.review(imported["key"], approved_by="founder",
                                   granted_tools=["text.summary"])
        self.assertEqual(reviewed["refused_unknown"], ["shell.exec"])
        self.advance()
        with self.assertRaises(SkillEcosystemError):
            self.eco.review(imported["key"], approved_by="founder",
                            granted_tools=["text.summary"])


class PipelineTests(EcosystemBase):
    def setUp(self):
        super().setUp()
        self.imported = self.eco.import_skill(manifest(), provided_by="founder")
        self.eco.review(self.imported["key"], approved_by="founder",
                        granted_tools=["text.summary", "search.obsidian"])
        self.key = self.imported["key"]
        self.advance()

    def test_bounded_pipeline_runs_granted_steps_only(self):
        result = self.eco.run_pipeline(
            self.key, "daily-flow",
            [{"op": "text.summary", "payload": {"text": "hello"}}], {"q": 1})
        self.assertEqual(result["status"], "ran")
        self.assertEqual(len(result["steps"]), 1)

    def test_ungranted_operation_is_refused_before_execution(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.run_pipeline(
                self.key, "sneaky",
                [{"op": "not.granted", "payload": {}}], {})
        # The refused op was registered after review, so the refusal is
        # grant-based even though the operation exists on the host.
        self.eco.register_operation("bulk.export", lambda ctx, prior: "data")
        with self.assertRaises(SkillEcosystemError) as caught:
            self.eco.run_pipeline(
                self.key, "exfiltrate", [{"op": "bulk.export"}], {})
        self.assertIn("not granted", str(caught.exception))

    def test_unregistered_operation_is_refused(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.run_pipeline(
                self.key, "unknown", [{"op": "shell.exec", "payload": {}}], {})

    def test_pipeline_bounds_and_dependency_order(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.run_pipeline(
                self.key, "long",
                [{"op": "text.summary"} for _ in range(13)], {})
        with self.assertRaises(SkillEcosystemError):
            self.eco.run_pipeline(
                self.key, "forward-dep",
                [{"op": "text.summary", "depends_on": "search.obsidian"},
                 {"op": "search.obsidian"}], {})

    def test_step_failure_is_measured_and_recorded(self):
        def broken(ctx, prior):
            raise RuntimeError("boom")
        self.eco.register_operation("text.summary", broken)
        result = self.eco.run_pipeline(
            self.key, "broken", [{"op": "text.summary"}], {})
        self.assertEqual(result["status"], "failed:RuntimeError")
        self.advance()
        runs = self.eco.runs(self.key)
        self.assertEqual(runs[0]["status"], "failed:RuntimeError")


class RollbackTests(EcosystemBase):
    def setUp(self):
        super().setUp()
        self.imported = self.eco.import_skill(manifest(), provided_by="founder")
        self.key = self.imported["key"]
        self.eco.review(self.key, approved_by="founder", granted_tools=[])
        self.advance()

    def test_revoke_requires_owner_and_disables_activation(self):
        with self.assertRaises(SkillEcosystemError):
            self.eco.revoke(self.key, approved_by="")
        revoked = self.eco.revoke(self.key, approved_by="founder")
        self.assertTrue(revoked["rolled_back"])
        listing = self.eco.list()
        self.assertEqual(listing[0]["status"], "revoked")
        self.advance()
        with self.assertRaises(SkillEcosystemError):
            self.eco.review(self.key, approved_by="founder", granted_tools=[])

    def test_unreviewed_import_uses_delete_semantics_not_revoke(self):
        second = self.eco.import_skill(
            manifest(instructions="other"), provided_by="founder")
        with self.assertRaises(SkillEcosystemError):
            self.eco.revoke(second["key"], approved_by="founder")

    def test_catalog_is_bounded(self):
        for i in range(39):
            self.eco.import_skill(
                manifest(instructions="text %d" % i, name="s%d" % i),
                provided_by="x")
        with self.assertRaises(SkillEcosystemError):
            self.eco.import_skill(
                manifest(instructions="over", name="overflow"), provided_by="x")


if __name__ == "__main__":
    unittest.main()
