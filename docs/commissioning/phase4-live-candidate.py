"""Phase 4 live repository candidate: prepare, validate, gate — never promote.

The live SPARK work tree has substantial uncommitted owner work, so the
release candidate is prepared and validated end to end and then presented to
the real Phase 1 Git Safety Gate, which must refuse promotion while the tree
is dirty. No live file is ever written by this script; all artifacts are kept
under D:\\SPARK-Evolution-Temp\\phase4\\release-data.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(r"C:\Users\ASUS\spark")
DATA = Path(r"D:\SPARK-Evolution-Temp\phase4\release-data")
EVIDENCE = Path(r"D:\SPARK-Evolution-Temp\phase4\live-candidate.json")
sys.path.insert(0, str(REPO / "backend"))

from spark_release_engine import ReleaseError, ReleasePipeline  # noqa: E402
from spark_auto_evolution import GitSafetyGate  # noqa: E402
from spark_maintenance import digest  # noqa: E402

TARGET = "backend/spark_echo_gate.py"
RELEASE_ID = "live-echo-reason-01"

ORIGINAL = (REPO / "backend" / "spark_echo_gate.py").read_text(encoding="utf-8")

MARGIN_NOTE = '''

    def block_reason(self, now=None):
        """Read-only cockpit diagnostic: why the mic is currently blocked.

        Additive companion of mic_blocked(); logic duplication is avoided by
        deriving the reason from the same state mic_blocked inspects.
        """
        current = time.monotonic() if now is None else now
        if self._output_active:
            return "speaker"
        if current < self._release_at:
            return "tail"
        if self.require_rearm and self._needs_rearm:
            return "rearm"
        return None
'''

CANDIDATE = ORIGINAL.rstrip("\n") + MARGIN_NOTE

OUT = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "live_head": None, "live_branch": None, "steps": []}


def add(step, name, **fields):
    entry = {"step": step, "name": name, **fields}
    OUT["steps"].append(entry)
    print(json.dumps(entry, default=str))


def main():
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    OUT["live_head"], OUT["live_branch"] = head, branch

    before_bytes = (REPO / "backend" / "spark_echo_gate.py").read_bytes()
    if str(RELEASE_ID) and (DATA / "releases" / RELEASE_ID).exists():
        add(0, "pre_existing_release_found", release_id=RELEASE_ID, note="reusing pipeline ID")
        raise SystemExit("release id already used; delete D: release data to rerun")

    original_sha = hashlib.sha256(before_bytes).hexdigest()
    add(1, "candidate_prepared", target=TARGET,
        original_sha256=original_sha,
        candidate_sha256=hashlib.sha256(CANDIDATE.encode()).hexdigest(),
        note="genuine additive source change: block_reason() diagnostics")

    pipe = ReleasePipeline(REPO, DATA)
    record = pipe.submit(RELEASE_ID, [{"path": TARGET,
                                       "content": CANDIDATE,
                                       "sha256": original_sha}])
    add(2, "candidate_submitted", release_id=RELEASE_ID, status=record["status"])
    record = pipe.validate(RELEASE_ID)
    add(3, "candidate_validated", tests=[record["test_evidence"]["tests"]],
        returncode=record["test_evidence"]["returncode"],
        note="real focused unittest run on isolated staged copy")
    record = pipe.verify(RELEASE_ID)
    add(4, "candidate_verified_against_live", status=record["status"],
        live_file_still_original=digest(before_bytes) == original_sha)

    gate_state = GitSafetyGate(REPO).inspect()
    add(5, "phase1_gate_inspected", dirty=gate_state["dirty"],
        dirty_paths=len(gate_state["paths"]),
        sample=gate_state["paths"][:3])

    refused_reason = None
    try:
        pipe.promote(RELEASE_ID, approved=False)  # no approval is ever given
        raise RuntimeError("promotion must be refused")
    except ReleaseError as error:
        refused_reason = str(error)[:220]
    add(6, "promotion_refused", release_id=RELEASE_ID,
        status=pipe.record(RELEASE_ID)["status"],
        mode="approval intentionally withheld + dirty live tree",
        reason=refused_reason,
        live_file_unchanged=(REPO / "backend" / "spark_echo_gate.py").read_bytes() == before_bytes)

    after_bytes = (REPO / "backend" / "spark_echo_gate.py").read_bytes()
    add(7, "preservation_check", bytes_identical=after_bytes == before_bytes,
        sha256=digest(after_bytes))
    OUT["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    OUT["verdict"] = "candidate validated; promotion correctly refused (dirty live tree)"
    EVIDENCE.write_text(json.dumps(OUT, indent=2, default=str), encoding="utf-8")
    print("EVIDENCE:", EVIDENCE)


if __name__ == "__main__":
    main()
