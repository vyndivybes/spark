"""Transactional release pipeline: journal, gates, rollback, crash recovery.

Offline acceptance: Git inspection and interaction are injected fakes; the
only real subprocess work is focused unittest discovery inside tiny staged
copies on temporary storage. The real SPARK work tree is never mutated.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_release_engine import ReleaseError, ReleasePipeline


class FakeGate:
    """Injected stand-in for the Phase 1 Git Safety Gate."""

    def __init__(self, dirty=False, error=None):
        self.dirty = dirty
        self.error = error

    def inspect(self):
        if self.error:
            raise self.error
        return {"dirty": self.dirty, "paths": ["README.md"] if self.dirty else []}


APP = '''"""Fixture application released through the pipeline."""
CASE = {word!r}


def speak():
    return "hello " + CASE


def shout():
    return speak().upper()
'''


def app(word):
    return APP.format(word=word)

TESTS = '''import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import app as module


class AppReleaseTests(unittest.TestCase):
    def test_speak(self):
        self.assertEqual(module.speak(), "hello {word}")

    def test_shout(self):
        self.assertEqual(module.shout(), ("hello {word}").upper())


if __name__ == "__main__":
    unittest.main()
'''


def sha(payload):
    return hashlib.sha256(payload if isinstance(payload, bytes)
                          else payload.encode()).hexdigest()


class ReleaseEngineTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="spark-release-test-")
        self.repo = Path(self.base) / "repo"
        self.data = Path(self.base) / "data"
        (self.repo / "backend").mkdir(parents=True)
        (self.repo / "tests").mkdir(parents=True)
        (self.repo / "backend" / "app.py").write_text(APP.format(word="world"), encoding="utf-8")
        (self.repo / "tests" / "test_app.py").write_text(TESTS.format(word="world"),
                                                           encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def pipeline(self, **kwargs):
        options = {"runner": self._runner, "health": self._health}
        options.update(kwargs)
        return ReleasePipeline(self.repo, self.data, **options)

    # injected runner: real unittest subprocess over the tiny staged copy
    def _runner(self, argv, **kwargs):
        argv = [sys.executable if arg == sys.executable else arg for arg in argv]
        return subprocess.run(argv, **kwargs)

    def _health(self, repository):
        import ast
        for source in (Path(repository) / "backend").glob("*.py"):
            ast.parse(source.read_text(encoding="utf-8-sig"), filename=source.name)
        if not (Path(repository) / "backend" / "app.py").is_file():
            return {"healthy": False, "findings": ["app.py missing"]}
        return {"healthy": True, "findings": []}

    def original(self):
        return (self.repo / "backend" / "app.py").read_text(encoding="utf-8")

    def original_bytes(self):
        return (self.repo / "backend" / "app.py").read_bytes()

    def digest(self):
        return sha(self.original_bytes())


class HappyPath(ReleaseEngineTests):
    def test_full_pipeline_accepts_release_a(self):
        original_text = self.original()
        candidate = original_text + '\n\ndef farewell():\n    return "goodbye " + CASE\n'
        pipe = self.pipeline(git_gate=FakeGate())
        record = pipe.submit("rel-a-0001", [{"path": "backend/app.py",
                                             "content": candidate, "sha256": self.digest()}])
        self.assertEqual(record["status"], "staged")
        self.assertEqual(record["changes"][0]["original_sha256"], self.digest())
        self.assertEqual(record["changes"][0]["candidate_sha256"], sha(candidate.encode()))
        record = pipe.validate("rel-a-0001")
        self.assertEqual(record["test_evidence"]["returncode"], 0)
        record = pipe.verify("rel-a-0001")
        self.assertEqual(record["status"], "verified")
        record = pipe.promote("rel-a-0001", approved=True)
        self.assertEqual(record["outcome"], "accepted")
        self.assertEqual(self.original(), candidate)
        self.assertEqual(record["health"]["healthy"], True)
        events = [entry["event"] for entry in pipe.history()]
        for expected in ("candidate", "validated", "verified", "activating", "accepted"):
            self.assertIn(expected, events)

    def test_promotion_requires_explicit_approval(self):
        pipe = self.pipeline(git_gate=FakeGate())
        pipe.submit("rel-a-0002", [{"path": "backend/app.py",
                                    "content": self.original() + "\ndef blocked():\n    return 'x2'\n",
                                    "sha256": self.digest()}])
        pipe.validate("rel-a-0002")
        pipe.verify("rel-a-0002")
        with self.assertRaises(ReleaseError):
            pipe.promote("rel-a-0002", approved=False)
        self.assertNotIn("def blocked", self.original())

    def test_validation_failure_refuses_promotion(self):
        broken = self.original() + "\ndef broken(:\n"
        pipe = self.pipeline(git_gate=FakeGate())
        with self.assertRaises(ReleaseError):
            pipe.submit("rel-b-0001", [{"path": "backend/app.py",
                                        "content": broken, "sha256": self.digest()}])
        # nothing was stored for an invalid candidate and nothing was changed
        self.assertFalse((self.data / "releases" / "rel-b-0001").exists())
        with self.assertRaises(ReleaseError):
            pipe.validate("rel-b-0001")

    def test_failing_focused_tests_refuse_release(self):
        bad = self.original().replace("return \"hello \" + CASE", "return \"bye \" + CASE")
        pipe = self.pipeline(git_gate=FakeGate())
        pipe.submit("rel-c-0001", [{"path": "backend/app.py",
                                    "content": bad, "sha256": self.digest()}])
        with self.assertRaises(ReleaseError):
            pipe.validate("rel-c-0001")
        self.assertIn("'world'", self.original())  # live tree untouched on refusal

    def test_release_id_reuse_and_unknown_release(self):
        pipe = self.pipeline(git_gate=FakeGate())
        pipe.submit("rel-d-0001", [{"path": "backend/app.py",
                                    "content": self.original() + "\n",
                                    "sha256": self.digest()}])
        with self.assertRaises(ReleaseError):
            pipe.submit("rel-d-0001", [{"path": "backend/app.py",
                                        "content": self.original(),
                                        "sha256": self.digest()}])
        with self.assertRaises(ReleaseError):
            pipe.record("nope-0000")


class StrictControls(ReleaseEngineTests):
    def candidate(self, pipe, release_id, content=None):
        content = content if content is not None else self.original() + "\n# release\n"
        return pipe.submit(release_id, [{"path": "backend/app.py",
                                         "content": content, "sha256": self.digest()}])

    def declaration(self):
        return self.pipeline(git_gate=FakeGate())

    def test_path_traversal_refused(self):
        pipe = self.declaration()
        for target in ("../outside.py", "backend/../../x.py", "backend/../x.py",
                       "C:/abs/x.py", "backend\\win.py", ".env", "backend/server.json",
                       "tests/evil.py", "backend/x.txt"):
            with self.assertRaises(ReleaseError):
                pipe.submit("trav-0001", [{"path": target,
                                           "content": self.original(),
                                           "sha256": self.digest()}])
        self.assertFalse(list((self.repo / "backend").glob("*.tmp")))

    def test_protected_file_refused_even_with_clean_tree(self):
        protected = self.repo / "backend" / "spark_maintenance.py"
        protected.write_text("# protected module\nVALUE = 1\n", encoding="utf-8")
        pipe = self.declaration()
        with self.assertRaises(ReleaseError):
            pipe.submit("prot-0001", [{"path": "backend/spark_maintenance.py",
                                       "content": "VALUE = 2\n",
                                       "sha256": sha(protected.read_text(encoding="utf-8"))}])

    def test_mismatched_original_sha_refused(self):
        pipe = self.declaration()
        with self.assertRaises(ReleaseError):
            pipe.submit("hash-0001", [{"path": "backend/app.py",
                                       "content": self.original(),
                                       "sha256": "0" * 64}])

    def test_secret_in_candidate_refused(self):
        smuggled = self.original() + ('\nTOKEN = "ghp_0123456789abcdefghij'
                                      'klmnopqrstuvwxyzAB"\n')
        pipe = self.declaration()
        with self.assertRaises(ReleaseError):
            self.candidate(pipe, "secr-0001", smuggled)

    def test_nonexistent_target_refused(self):
        pipe = self.declaration()
        with self.assertRaises(ReleaseError):
            pipe.submit("miss-0001", [{"path": "backend/ghost.py",
                                       "content": "# ghost\n",
                                       "sha256": sha("# ghost\n")}])

    def test_dirty_git_tree_blocks_promotion_and_preserves_tree(self):
        pipe = self.pipeline(git_gate=FakeGate(dirty=True))
        record = self.candidate(pipe, "dirt-0001")
        pipe.validate("dirt-0001")
        pipe.verify("dirt-0001")
        with self.assertRaises(ReleaseError):
            pipe.promote("dirt-0001", approved=True)
        self.assertEqual(self.original().count('# release\n'), 0)
        self.assertEqual(pipe.record("dirt-0001")["status"], "refused")
        self.assertEqual(record["status"], "staged")

    def test_git_unavailable_fails_closed(self):
        class BrokenGate:
            def inspect(self):
                raise RuntimeError("git missing")

        pipe = self.pipeline(git_gate=BrokenGate())
        self.candidate(pipe, "unav-0001")
        pipe.validate("unav-0001")
        pipe.verify("unav-0001")
        with self.assertRaises(ReleaseError):
            pipe.promote("unav-0001", approved=True)
        self.assertEqual(pipe.record("unav-0001")["status"], "refused")


class RollbackAndRecovery(ReleaseEngineTests):
    def stage_ready(self, release_id, health=None):
        # additive candidates keep the focused-test contract intact
        marker = release_id.split("-")[1]
        candidate = self.original() + ("\n\ndef resilient_%s():\n    return CASE\n" % marker)
        pipe = self.pipeline(git_gate=FakeGate(), **({"health": health} if health else {}))
        pipe.submit(release_id, [{"path": "backend/app.py",
                                  "content": candidate, "sha256": self.digest()}])
        pipe.validate(release_id)
        pipe.verify(release_id)
        return pipe, candidate

    def test_failed_health_check_rolls_back_exactly(self):
        def sick(repository):
            return {"healthy": False, "findings": ["simulated failure"]}

        pipe, candidate = self.stage_ready("rb-a-0001", health=sick)
        record = pipe.promote("rb-a-0001", approved=True)
        self.assertEqual(record["outcome"], "rolled_back")
        # byte-exact restoration to the pre-release original:
        self.assertEqual(sha(self.original()), sha(APP.format(word="world")))
        self.assertEqual(pipe.record("rb-a-0001")["status"], "rolled_back")

    def test_manual_rollback_after_accept(self):
        pipe, candidate = self.stage_ready("rb-b-0001")
        record = pipe.promote("rb-b-0001", approved=True)
        self.assertEqual(self.original(), candidate)
        record = pipe.rollback("rb-b-0001", reason="operator revert")
        self.assertEqual(record["outcome"], "rolled_back")
        self.assertEqual(sha(self.original()), sha(APP.format(word="world")))

    def test_conflicting_owner_edit_blocks_recovery_with_snapshot_retained(self):
        pipe, candidate = self.stage_ready("rb-c-0001")
        record = pipe.promote("rb-c-0001", approved=True)
        # owner edits the released file after acceptance
        (self.repo / "backend" / "app.py").write_text(APP.format(word="owner."), encoding="utf-8")
        with self.assertRaises(ReleaseError):
            pipe.rollback("rb-c-0001")
        self.assertEqual((self.repo / "backend" / "app.py").read_text(encoding="utf-8"),
                         APP.format(word="owner."))  # owner edit preserved
        self.assertIn("snapshot", {p.name for p in (self.data / "releases" / "rb-c-0001").iterdir()})

    def test_interruption_during_activation_recovers_on_restart(self):
        pipe, candidate = self.stage_ready("rc-a-0001")
        accepted = pipe.promote("rc-a-0001", approved=True)
        folder = self.data / "releases" / "rc-a-0001"
        self.assertEqual(accepted["outcome"], "accepted")
        # simulate a kill while "activating": journal stuck, candidate write not landed
        stuck = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        stuck["status"] = "activating"
        (folder / "manifest.json").write_text(json.dumps(stuck), encoding="utf-8")
        (self.repo / "backend" / "app.py").write_bytes(self.original_bytes())
        restarted = ReleasePipeline(self.repo, self.data, git_gate=FakeGate())
        self.assertEqual(restarted.recovered, ["rc-a-0001"])
        self.assertEqual(sha(self.original()), sha(APP.format(word="world")))
        self.assertEqual(restarted.record("rc-a-0001")["status"], "recovered")
        events = [entry["event"] for entry in restarted.history()]
        self.assertIn("recovered", events)

    def test_recovery_conflict_flags_release_for_review(self):
        pipe, candidate = self.stage_ready("rc-b-0001")
        folder = self.data / "releases" / "rc-b-0001"
        record = pipe.record("rc-b-0001")
        record["status"] = "activating"
        (folder / "manifest.json").write_text(json.dumps(record), encoding="utf-8")
        (folder / "snapshot").mkdir(exist_ok=True)
        (folder / "snapshot" / "app.py").write_bytes(b"corrupt")
        restarted = ReleasePipeline(self.repo, self.data, git_gate=FakeGate())
        self.assertEqual(restarted.recovered, [])
        self.assertEqual(restarted.record("rc-b-0001")["status"], "refused")
        # live file untouched despite the broken snapshot
        self.assertIn("'world'", self.original())


class SequentialDays(ReleaseEngineTests):
    def test_no_daily_ceiling_between_sequential_releases(self):
        frozen = 1760000000.0  # all promotions inside one simulated UTC day
        pipe = self.pipeline(git_gate=FakeGate(), clock=lambda: frozen)
        words = ["a", "b", "c"]
        for index, word in enumerate(words, start=1):
            release_id = "seq-%04d" % index
            candidate = self.original() + (
                "\n\ndef feature_%s():\n    return CASE\n" % word)
            original_sha = self.digest()
            pipe.submit(release_id, [{"path": "backend/app.py",
                                      "content": candidate, "sha256": original_sha}])
            pipe.validate(release_id)
            pipe.verify(release_id)
            record = pipe.promote(release_id, approved=True)
            self.assertEqual(record["outcome"], "accepted")
            self.assertEqual(self.original(), candidate)
            events = [entry["event"] for entry in pipe.history()]
            self.assertEqual(events.count("accepted"), index)
        accepts = [entry for entry in pipe.history() if entry["event"] == "accepted"]
        days = {entry["ts"] // 86400 for entry in accepts}
        self.assertLessEqual(len(days), 1)  # no daily upgrade ceiling on this pipeline


class SymlinkDefenses(ReleaseEngineTests):
    def test_symlink_target_refused(self):
        if not hasattr(__import__("os"), "symlink"):
            self.skipTest("symlinks unavailable")
        import os
        pipe = self.pipeline(git_gate=FakeGate())
        target = self.repo / "backend" / "linkme.py"
        try:
            os.symlink(self.repo / "backend" / "app.py", target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation requires privilege")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        with self.assertRaises(ReleaseError):
            pipe.submit("sync-0001", [{"path": "backend/linkme.py",
                                       "content": "# linked\n",
                                       "sha256": sha("# linked\n")}])

    def test_storage_symlink_refused(self):
        if not hasattr(__import__("os"), "symlink"):
            self.skipTest("symlinks unavailable")
        import os
        real = Path(self.base) / "elsewhere"
        real.mkdir()
        try:
            os.symlink(real, self.data / "releases" / "slinks-01")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation requires privilege")
        pipe = self.pipeline(git_gate=FakeGate())
        with self.assertRaises(ReleaseError):
            pipe.record("slinks-01")


class Staleness(ReleaseEngineTests):
    def test_concurrent_owner_edit_before_promotion_refuses(self):
        pipe = self.pipeline(git_gate=FakeGate())
        candidate = self.original() + "\n# candidate\n"
        pipe.submit("stal-0001", [{"path": "backend/app.py",
                                   "content": candidate, "sha256": self.digest()}])
        pipe.validate("stal-0001")
        # concurrent owner modification between staging and promotion
        (self.repo / "backend" / "app.py").write_text(
            self.original() + "\n# owner tweak\n", encoding="utf-8")
        with self.assertRaises(ReleaseError):
            pipe.verify("stal-0001")
        self.assertFalse((self.repo / "backend" / "app.py").read_text(
            encoding="utf-8").endswith("# candidate\n"))
        with self.assertRaises(ReleaseError):
            pipe.promote("stal-0001", approved=True)

    def test_verify_then_concurrent_edit_then_promotion_refused(self):
        pipe = self.pipeline(git_gate=FakeGate())
        candidate = self.original() + "\n# attempt\n"
        pipe.submit("stal-0002", [{"path": "backend/app.py",
                                   "content": candidate, "sha256": self.digest()}])
        pipe.validate("stal-0002")
        pipe.verify("stal-0002")
        (self.repo / "backend" / "app.py").write_text(
            self.original() + "\n# owner tweak\n", encoding="utf-8")
        with self.assertRaises(ReleaseError):
            pipe.promote("stal-0002", approved=True)
        self.assertIn("# owner tweak", self.original())
        self.assertNotIn("# attempt", self.original())


if __name__ == "__main__":
    unittest.main()
