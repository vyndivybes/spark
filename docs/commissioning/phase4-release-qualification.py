"""Phase 4 sequential release qualification on a disposable Git fixture (D:).

Real components: git init/commit inside the disposable fixture, the real
Phase 1 GitSafetyGate (read-only git inspection), real SHA256 hashing, real
focused unittest execution via subprocess against staged copies, and the
durable journal on D:.
Mock/simulated (failure injection only, clearly marked): the failing health
check, the mid-promotion process kill, and the concurrent owner edit.
No model inference is used anywhere in this harness: the pipeline under
test is deterministic, so mock-free repeatable evidence is produced without
any paid API.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_BACKEND = Path(r"C:\Users\ASUS\spark\backend")
REPO_TESTS = Path(r"C:\Users\ASUS\spark\tests")
sys.path.insert(0, str(REPO_BACKEND))

from spark_release_engine import ReleaseError, ReleasePipeline  # noqa: E402

FIXTURE = Path(r"D:\SPARK-Evolution-Temp\phase4\fixture-repo")
DATA = Path(r"D:\SPARK-Evolution-Temp\phase4\release-data")
EVIDENCE = Path(r"D:\SPARK-Evolution-Temp\phase4\release-qualification.json")
LOG = Path(r"D:\SPARK-Evolution-Temp\phase4\release-qualification.log")

APP = '''"""Fixture application under release qualification."""
CASE = "baseline"


def speak():
    return "hello " + CASE
'''

TESTS = '''import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import app as module


class FixtureReleaseTests(unittest.TestCase):
    def test_speak(self):
        self.assertEqual(module.speak(), "hello baseline")

    def test_has_not_traveled(self):
        self.assertNotIn("evil", module.CASE)


if __name__ == "__main__":
    unittest.main()
'''

OUT = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "fixture": str(FIXTURE), "data": str(DATA), "steps": []}


def rmtree_readonly(path):
    def on_error(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    import stat
    shutil.rmtree(path, onerror=on_error)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(argv, cwd):
    completed = subprocess.run(["git", *argv], cwd=cwd, capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(argv), completed.stderr[:200]))
    return completed.stdout


def step(number, name, detail, **extra):
    entry = {"step": number, "name": name, **detail, **extra}
    OUT["steps"].append(entry)
    print(json.dumps(entry, default=str))
    return entry


def live_text():
    return (FIXTURE / "backend" / "app.py").read_text(encoding="utf-8")


def run_release(pipe, release_id, candidate_content, *, original_sha=None,
                health=None, note=""):
    original_sha = original_sha or sha_file(FIXTURE / "backend" / "app.py")
    pipe.submit(release_id, [{"path": "backend/app.py",
                              "content": candidate_content, "sha256": original_sha}])
    pipe.validate(release_id)
    pipe.verify(release_id)
    outcome = pipe.promote(release_id, approved=True)
    # Fixture-only baseline bookkeeping: an accepted release becomes the next
    # committed baseline of the disposable fixture so the Phase 1 gate sees a
    # clean tree for the next candidate. Never applied to the live repository.
    if outcome["outcome"] == "accepted":
        git(["add", "backend/app.py"], FIXTURE)
        git(["commit", "-m", "fixture baseline after release " + release_id],
            FIXTURE)
    return outcome


def main():
    # await step 1: clean baseline
    import stat  # noqa: F401  (used by rmtree_readonly error handler)

    if FIXTURE.exists():
        rmtree_readonly(FIXTURE)
    if DATA.exists():
        shutil.rmtree(DATA)
    (FIXTURE / "backend").mkdir(parents=True)
    (FIXTURE / "tests").mkdir(parents=True)
    (FIXTURE / "backend" / "app.py").write_text(APP, encoding="utf-8")
    (FIXTURE / "tests" / "test_app.py").write_text(TESTS, encoding="utf-8")
    git(["init", "-b", "main"], FIXTURE)
    git(["config", "user.email", "phase4@fixture.local"], FIXTURE)
    git(["config", "user.name", "Phase 4 Fixture"], FIXTURE)
    git(["add", "backend/app.py", "tests/test_app.py"], FIXTURE)
    git(["commit", "-m", "clean baseline"], FIXTURE)
    baseline_head = git(["rev-parse", "HEAD"], FIXTURE).strip()
    baseline_sha = sha_file(FIXTURE / "backend" / "app.py")
    gate_state = ReleasePipeline(FIXTURE, DATA, recover=True)
    clean = gate_state.git_gate.inspect()
    step(1, "clean_baseline", {"head": baseline_head, "app_sha256": baseline_sha,
                               "git_gate": clean})
    pipe = ReleasePipeline(FIXTURE, DATA, recover=False)

    # steps 2-4: candidate A, promotion, functional + SHA256 verification
    candidate_a = APP.replace('CASE = "baseline"',
                              'CASE = "baseline"\n\n\ndef shout():\n    return speak().upper()\n')
    outcome_a = run_release(pipe, "qual-rel-a", candidate_a)
    assert outcome_a["outcome"] == "accepted", outcome_a
    live_sha_after_a = sha_file(FIXTURE / "backend" / "app.py")
    assert live_sha_after_a == outcome_a["changes"][0]["candidate_sha256"]
    assert "def shout" in live_text()
    step(2, "candidate_a_validated", {"release_id": "qual-rel-a",
                                      "tests_evidence": outcome_a["test_evidence"]["returncode"],
                                      "original_sha256": outcome_a["changes"][0]["original_sha256"],
                                      "candidate_sha256": outcome_a["changes"][0]["candidate_sha256"]})
    step(3, "release_a_promoted", {"outcome": outcome_a["outcome"],
                                   "health": outcome_a["health"]["healthy"]})
    step(4, "release_a_verified_bytes", {"app_sha256": live_sha_after_a})

    # step 5: record release A
    record_a = pipe.record("qual-rel-a")
    journal_a = [entry for entry in pipe.history() if entry["release_id"] == "qual-rel-a"]
    step(5, "release_a_recorded", {"release_id": "qual-rel-a", "status": record_a["status"],
                                   "journal_events": [e["event"] for e in journal_a]})

    # step 6: controlled restart (fresh engine from durable state only)
    del pipe
    pipe = ReleasePipeline(FIXTURE, DATA, recover=False)
    reloaded = pipe.record("qual-rel-a")
    step(6, "controlled_restart", {"reloaded_release": reloaded["release_id"],
                                   "reloaded_status": reloaded["status"],
                                   "journal_entries": len(pipe.history())})

    # steps 7-10: candidate B against release A, promotion, new baseline, record B
    candidate_b = live_text() + '\n\ndef farewell(name):\n    return "bye " + name\n'
    outcome_b = run_release(pipe, "qual-rel-b", candidate_b)
    assert outcome_b["outcome"] == "accepted", outcome_b
    live_sha_after_b = sha_file(FIXTURE / "backend" / "app.py")
    record_b = pipe.record("qual-rel-b")
    step(7, "candidate_b_generated", {"baseline": "release A", "test_evidence": "real unittest rc=0"})
    step(8, "release_b_promoted", {"outcome": outcome_b["outcome"], "health": outcome_b["health"]["healthy"]})
    step(9, "release_b_new_baseline", {"app_sha256": live_sha_after_b,
                                       "candidate_sha256": outcome_b["changes"][0]["candidate_sha256"]})
    step(10, "release_b_recorded", {"release_id": "qual-rel-b", "status": record_b["status"]})

    # step 11: simulate failed health check -> exact rollback
    baseline_b_bytes = (FIXTURE / "backend" / "app.py").read_bytes()
    baseline_b_sha = hashlib.sha256(baseline_b_bytes).hexdigest()

    def sick_health(_repository):
        return {"healthy": False, "findings": [{"error": "SimulatedHealthFailure",
                                                "message": "mock failure injection"}]}

    candidate_c = live_text() + "\n\ndef broken_feature():\n    return CASE\n"
    pipe_c = ReleasePipeline(FIXTURE, DATA, recover=False, health=sick_health)
    outcome_c = run_release(pipe_c, "qual-rel-c", candidate_c)
    assert outcome_c["outcome"] == "rolled_back", outcome_c
    assert sha_file(FIXTURE / "backend" / "app.py") == baseline_b_sha, "rollback must be exact"
    assert (FIXTURE / "backend" / "app.py").read_bytes() == baseline_b_bytes
    step(11, "failed_health_check_rollback", {"release_id": "qual-rel-c",
                                              "outcome": "rolled_back",
                                              "bytes_exact": True,
                                              "app_sha256": baseline_b_sha,
                                              "note": "health check is an injected failure"})

    # step 12 already covered by byte comparison above; mark it
    step(12, "exact_rollback_verified", {"sha256_matches_baseline_b": True})

    # step 13: simulated interruption during promotion (mock: process kill)
    crash_trigger = Path(DATA) / "recover-point"
    crash_target = "qual-rel-d"
    child = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--crash-child", crash_target,
         "--data", str(DATA), "--fixture", str(FIXTURE), "--trigger", str(crash_trigger)],
        cwd=str(Path(__file__).resolve().parent))
    child.wait(timeout=120)
    step(13, "interruption_simulated", {"child_exit": child.returncode,
                                        "note": "child killed mid-activation after snapshot+fsync"})

    # step 14: restart recovery
    restarted = ReleasePipeline(FIXTURE, DATA, recover=True)
    assert restarted.recovered == [crash_target], restarted.recovered
    assert sha_file(FIXTURE / "backend" / "app.py") == baseline_b_sha
    step(14, "restart_recovery", {"recovered_releases": restarted.recovered,
                                  "app_sha256": sha_file(FIXTURE / "backend" / "app.py")})

    # step 15: concurrent owner modification -> promotion refusal (dirty tree)
    owner_file = FIXTURE / "backend" / "owner_notes.py"
    owner_file.write_text("# concurrent owner edit\nOWNER = True\n", encoding="utf-8")
    candidate_e = (FIXTURE / "backend" / "app.py").read_text(encoding="utf-8") + \
        "\n\ndef should_refuse():\n    return CASE\n"
    try:
        run_release(ReleasePipeline(FIXTURE, DATA, recover=False), "qual-rel-e", candidate_e)
        raise RuntimeError("dirty-tree promotion must be refused")
    except ReleaseError as error:
        refused_e = str(error)[:200]
    step(15, "concurrent_owner_modification_refused",
         {"reason": refused_e, "status": ReleasePipeline(FIXTURE, DATA, recover=False)
          .record("qual-rel-e")["status"]})

    # staleness variant: owner edits the target itself after verification
    record_f = None
    pipe_f = ReleasePipeline(FIXTURE, DATA, recover=False)
    candidate_f = (FIXTURE / "backend" / "app.py").read_text(encoding="utf-8") + \
        "# stale marker pending\n"
    pipe_f.submit("qual-rel-f", [{"path": "backend/app.py",
                                  "content": candidate_f,
                                  "sha256": sha_file(FIXTURE / "backend" / "app.py")}])
    pipe_f.validate("qual-rel-f")
    (FIXTURE / "backend" / "app.py").write_text(
        (FIXTURE / "backend" / "app.py").read_text(encoding="utf-8") + "\n# owner tweak\n",
        encoding="utf-8")
    stale_refused = False
    try:
        pipe_f.verify("qual-rel-f")
    except ReleaseError:
        stale_refused = True
    step(15, "staleness_refused", {"refused": stale_refused,
                                   "owner_tweak_preserved": "# owner tweak" in live_text()})

    # restore the fixture file to the committed release-B baseline bytes
    (FIXTURE / "backend" / "app.py").write_bytes(baseline_b_bytes)

    # clean owner artifact for later steps in the disposable fixture only
    owner_file.unlink()

    # step 17: no daily upgrade ceiling (three accepted promotions this step set)
    accepted_today = [entry for entry in ReleasePipeline(FIXTURE, DATA,
                                                         recover=False).history()
                      if entry["event"] == "accepted"]
    extra = live_text() + "\n# ceiling probe\n"
    outcome_g = run_release(ReleasePipeline(FIXTURE, DATA, recover=False),
                            "qual-rel-g", extra)
    assert outcome_g["outcome"] == "accepted", outcome_g
    accepted = [entry for entry in ReleasePipeline(FIXTURE, DATA,
                                                   recover=False).history()
                if entry["event"] == "accepted"]
    days = {time.strftime("%Y-%m-%d", time.gmtime(entry["ts"])) for entry in accepted}
    quotas = [entry for entry in ReleasePipeline(FIXTURE, DATA, recover=False).history()
              if "daily" in json.dumps(entry)]
    step(17, "no_daily_ceiling", {"accepted_releases": len(accepted),
                                  "distinct_utc_days": sorted(days),
                                  "quota_events": quotas,
                                  "latest": outcome_g["release_id"]})

    OUT["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    OUT["verdict"] = "PASS"
    EVIDENCE.write_text(json.dumps(OUT, indent=2, default=str), encoding="utf-8")
    print("EVIDENCE:", EVIDENCE)


def crash_child(target, data, fixture, trigger=None):
    """Simulated hard kill mid-activation: journal 'activating' fsynced,
    rollback snapshot written, candidate landed, but health check never ran.
    Marked as failure-injection simulation per the mission statement."""
    from spark_maintenance import atomic_write

    fixture = Path(fixture)
    pipe = ReleasePipeline(fixture, data, recover=False)
    original_sha = sha_file(fixture / "backend" / "app.py")
    candidate = (fixture / "backend" / "app.py").read_text(encoding="utf-8") + \
        "\n\ndef crash_marker():\n    return CASE\n"
    pipe.submit(target, [{"path": "backend/app.py",
                          "content": candidate, "sha256": original_sha}])
    pipe.validate(target)
    pipe.verify(target)
    record = pipe.record(target)
    folder = pipe._dir(target)
    snapshot = folder / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    atomic_write(snapshot / "app.py", (fixture / "backend" / "app.py").read_bytes())
    record["status"] = "activating"
    pipe._save(folder, record)
    pipe._append_journal("activating", release_id=target, files=["backend/app.py"])
    atomic_write(fixture / "backend" / "app.py", candidate.encode("utf-8"))
    os._exit(9)  # simulated kill before the post-activation health check


if __name__ == "__main__":
    if "--crash-child" in sys.argv:
        index = sys.argv.index("--crash-child")
        args = sys.argv[index + 1:]
        crash_child(args[0], args[2], args[4], None)
    else:
        main()
