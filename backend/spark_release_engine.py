"""Transactional release pipeline for controlled SPARK upgrades.

Stages: Candidate -> Validate -> Stage -> Verify -> Safety Gate ->
Promote -> Health Check -> Accept or Rollback.

The pipeline composes the existing Phase 1 Git Safety Gate (read-only
`git status/rev-parse` inspection, never mutates the work tree) with a
durable, restart-safe release journal. Controls enforced per release:

- Manifest of original and candidate SHA256 for every affected file.
- Strict allowed-path checks: only existing backend Python files.
- Protected-file checks: recovery and authorization sources are never
  accepted as autonomous release targets.
- No symlinks anywhere in the considered paths, storage or targets.
- No path traversal: relative POSIX two-segment paths only.
- Candidate content must parse as Python, pass the secret scan and fit
  the bounded size limit.
- Focused test evidence is executed on an isolated staged copy and is
  linked to the release identifier in the durable journal.
- Activation is atomic per file and writes the rollback snapshot of the
  affected files only, plus an fsynced "activating" journal record,
  before the first live byte changes.
- Post-activation functional health verification; failure triggers exact
  rollback of the affected files only.
- Recovery: a release found in "activating" state at startup is rolled
  back from its verified snapshot (restart-safe after interruption).
- Promotion is refused when the Git work tree is dirty or when Git state
  cannot be verified (fail closed, Phase 1 gate never weakened).
- The pipeline never mutates Git state: no adds, commits, resets or
  checkouts, and no unattended commits of owner work.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

from spark_auto_evolution import AutoEvolutionError, GitSafetyGate, PROTECTED
from spark_maintenance import atomic_write, digest
from spark_repo_upgrade import linked
from spark_security_scan import scan_secrets


class ReleaseError(ValueError):
    pass


ALLOWED_ROOTS = frozenset({"backend"})
ALLOWED_SUFFIXES = frozenset({".py"})
MAX_CONTENT_BYTES = 65536
RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
STATUSES = frozenset({"staged", "verified", "accepted", "rolled_back",
                      "recovered", "refused"})
APPLYING_STATUSES = frozenset({"activating"})
DEFAULT_VALIDATION_TIMEOUT = 240


def _safe_relative(path):
    """Validate a strictly bounded relative POSIX path (no traversal)."""
    if not isinstance(path, str) or not path or "\\" in path:
        raise ReleaseError("Release paths must be POSIX relative paths.")
    pure = PurePosixPath(path)
    if pure.is_absolute() or not pure.parts or pure.parts[0] == "/":
        raise ReleaseError("Release paths must be repository-relative: " + path)
    if any(part in ("", ".", "..") for part in pure.parts):
        raise ReleaseError("Path traversal is prohibited: " + path)
    if any(":" in part for part in pure.parts):
        raise ReleaseError("Drive letters are prohibited: " + path)
    if len(pure.parts) != 2 or pure.parts[0] not in ALLOWED_ROOTS:
        raise ReleaseError("Release paths must target backend/<module>.py: " + path)
    if pure.suffix not in ALLOWED_SUFFIXES:
        raise ReleaseError("Only Python sources are released: " + path)
    if pure.name in PROTECTED:
        raise ReleaseError("Protected file requires a reviewed manual upgrade: " + path)
    return pure


def default_health(repository):
    """Functional health floor: every backend source must parse cleanly."""
    findings = []
    for source in sorted((Path(repository) / "backend").glob("*.py")):
        if source.is_symlink():
            findings.append({"path": "backend/" + source.name, "error": "linked source"})
            continue
        try:
            ast.parse(source.read_text(encoding="utf-8-sig"), filename=source.name)
        except (SyntaxError, UnicodeError, OSError) as error:
            findings.append({"path": "backend/" + source.name, "error": str(error)[:180]})
    return {"healthy": not findings, "findings": findings}


class ReleasePipeline:
    """Durable candidate -> acceptance/release/rollback state machine."""

    def __init__(self, repository, data_dir, *, clock=time.time, git_gate=None,
                 health=None, runner=None, recover=True):
        self.root = Path(repository).resolve()
        self.data = Path(data_dir).resolve()
        self.releases_dir = self.data / "releases"
        self.journal_file = self.releases_dir / "journal.jsonl"
        self.clock = clock
        self._runner = runner
        self.health = health or default_health
        self.git_gate = git_gate
        if self.git_gate is None:
            self.git_gate = GitSafetyGate(self.root)
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        self._verify_storage()
        if recover:
            self.recovered = self.recover()

    # ------------------------------------------------------------------
    # storage and journal primitives
    # ------------------------------------------------------------------
    def _verify_storage(self):
        if self.data.is_symlink() or self.releases_dir.is_symlink():
            raise ReleaseError("Linked release storage is prohibited.")
        if not self.root.is_dir():
            raise ReleaseError("Release repository root is missing.")

    def _append_journal(self, event, **fields):
        record = {"ts": round(self.clock(), 3), "event": event, **fields}
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        with self.journal_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record

    def _dir(self, release_id):
        if not isinstance(release_id, str) or not RELEASE_ID_PATTERN.match(release_id):
            raise ReleaseError("Release identifiers use [A-Za-z0-9._-]{4,64}.")
        folder = self.releases_dir / release_id
        if folder.is_symlink() or folder.parent.is_symlink():
            raise ReleaseError("Linked release folder is prohibited.")
        return folder

    def record(self, release_id):
        folder = self._dir(release_id)
        manifest_path = folder / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ReleaseError("Unknown release: " + release_id)
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def history(self, limit=200):
        try:
            lines = self.journal_file.read_text(
                encoding="utf-8").replace("\r\n", "\n").split("\n")
        except OSError:
            return []
        return [json.loads(line) for line in lines[-limit:] if line and not line.isspace()]

    def _save(self, folder, record):
        atomic_write(folder / "manifest.json", json.dumps(record, indent=2).encode("utf-8"))

    # ------------------------------------------------------------------
    # stage 1: candidate
    # ------------------------------------------------------------------
    def submit(self, release_id, changes, *, provenance=None):
        """Accept a candidate under strict path, protection and hashing rules."""
        folder = self._dir(release_id)
        if (folder / "manifest.json").exists():
            raise ReleaseError("Release identifier already exists: " + release_id)
        if not isinstance(changes, list) or not 1 <= len(changes) <= 4:
            raise ReleaseError("A release contains one to four file replacements.")
        manifest_changes, written = [], []
        for change in changes:
            if not isinstance(change, dict) or set(change) != {"path", "content", "sha256"}:
                raise ReleaseError("Each change needs path, content and original sha256.")
            relative = _safe_relative(change["path"])
            rel = relative.as_posix()
            path = self.root / relative
            if linked(path) or linked(path.parent):
                raise ReleaseError("Linked source is prohibited: " + rel)
            if not path.is_file() or path.suffix != ".py":
                raise ReleaseError("Release targets must be existing backend sources: " + rel)
            original = path.read_bytes()
            if digest(original) != change["sha256"]:
                raise ReleaseError(
                    "Original SHA256 mismatch for " + rel +
                    "; the live file changed since the candidate was made.")
            content = change["content"]
            if not isinstance(content, str) or not content:
                raise ReleaseError("Candidate content must be a non-empty string.")
            encoded = content.encode("utf-8")
            if len(encoded) > MAX_CONTENT_BYTES:
                raise ReleaseError("Candidate exceeds the %d KiB release limit."
                                   % (MAX_CONTENT_BYTES // 1024))
            try:
                ast.parse(content, filename=rel)
            except SyntaxError as error:
                raise ReleaseError("Candidate Python syntax is invalid (%s): %s"
                                   % (rel, str(error)[:140])) from None
            for finding in scan_secrets(content, rel):
                raise ReleaseError("Candidate secret scan finding in %s: %s" % (rel, str(finding)[:160]))
            candidate_dir = folder / "candidate"
            candidate_file = candidate_dir / relative.name
            candidate_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(candidate_file, encoded)
            if digest(candidate_file.read_bytes()) != digest(encoded):
                raise ReleaseError("Candidate storage integrity check failed: " + rel)
            manifest_changes.append({
                "path": relative.as_posix(),
                "original_sha256": change["sha256"],
                "candidate_sha256": digest(encoded),
            })
            written.append((candidate_file, encoded))
        record = {
            "release_id": release_id,
            "status": "staged",
            "created": round(self.clock(), 3),
            "repository": str(self.root),
            "changes": manifest_changes,
            "provenance": provenance or "owner-directed pipeline candidate",
        }
        self._save(folder, record)
        self._append_journal("candidate", release_id=release_id,
                             files=[change["path"] for change in manifest_changes])
        return record

    # ------------------------------------------------------------------
    # stage 2: validate (isolated staged copy, focused tests, evidence)
    # ------------------------------------------------------------------
    def _focused_tests(self, relative):
        token = re.sub(r"[^a-z0-9_]", "", Path(relative).stem.lower().replace("spark_", ""))
        if not token:
            return []
        hits = []
        for path in sorted((self.root / "tests").glob("test_*" + token + "*.py")):
            if path.is_file() and not linked(path):
                hits.append(Path("tests") / path.name)
        return hits[:6]

    def _closure(self, target, tests):
        wanted = {}
        queue, start = [target, *tests], set()
        while queue:
            relative = queue.pop(0)
            if relative in start:
                continue
            start.add(relative)
            path = self.root / relative
            if not path.is_file():
                continue
            if linked(path) or linked(path.parent):
                raise ReleaseError("Linked staged source is prohibited: " + relative.as_posix())
            data = path.read_bytes()
            wanted[relative.as_posix()] = data
            text = data.decode("utf-8-sig", errors="replace")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
            for name in names - {"__future__"}:
                for guess in ("backend/" + name + ".py",):
                    queue.append(Path(guess))
        return wanted

    def validate(self, release_id, *, tests=None, timeout=DEFAULT_VALIDATION_TIMEOUT):
        """Run focused tests on an isolated staged copy; link evidence to the release."""
        record = self.record(release_id)
        folder = self._dir(release_id)
        if record["status"] not in ("staged", "verified"):
            raise ReleaseError("Release is no longer in a validatable state.")
        if not isinstance(timeout, int) or not 60 <= timeout <= 600:
            raise ReleaseError("Validation timeout must be 60-600 seconds.")
        targets = [Path(change["path"]) for change in record["changes"]]
        tests = tests if tests is not None else []
        for target in targets:
            tests.extend(self._focused_tests(target))
        wanted = {}
        for target in targets:
            wanted.update(self._closure(target, tests))
        stage = folder / "stage"
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        for relative, data in wanted.items():
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            for change in record["changes"]:
                if relative == change["path"]:
                    data = (folder / "candidate" / Path(relative).name).read_bytes()
            destination.write_bytes(data)
        evidence = {
            "release_id": release_id,
            "command": [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                        "-p", "test_*.py"],
            "files": sorted(wanted),
            "tests": [t.as_posix() for t in tests],
        }
        findings = []
        if tests:
            runner = self._runner or subprocess.run
            try:
                completed = runner(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                     "-p", "test_*.py"],
                    cwd=stage, capture_output=True, timeout=timeout, text=True,
                    encoding="utf-8", errors="replace",
                    env={**{key: value for key, value in os.environ.items()
                            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                                               "COMSPEC", "PATHEXT", "LOCALAPPDATA",
                                               "APPDATA", "USERPROFILE"}},
                         "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
            except subprocess.TimeoutExpired:
                findings.append("Focused validation timed out.")
            except (OSError, ValueError) as error:
                findings.append("Focused validation could not run: " + str(error)[:140])
            else:
                evidence["returncode"] = completed.returncode
                evidence["tail"] = ((completed.stdout or "") +
                                    (completed.stderr or ""))[-1600:]
                if completed.returncode != 0:
                    findings.append("Focused validation tests failed.")
        else:
            evidence["returncode"] = 0
            evidence["tail"] = "no focused tests matched; syntax/secret checks only"
        record["test_evidence"] = evidence
        if findings:
            record["status"] = "refused"
            record["refused"] = findings
            self._save(folder, record)
            self._append_journal("refused", release_id=release_id, reason=findings[:2])
            raise ReleaseError("Release validation failed: " + "; ".join(findings))
        self._save(folder, record)
        self._append_journal("validated", release_id=release_id,
                             returncode=evidence.get("returncode"),
                             tests=len(tests))
        return record

    # ------------------------------------------------------------------
    # stage 3: verify (staleness against the live tree)
    # ------------------------------------------------------------------
    def verify(self, release_id):
        """Reconfirm every original SHA256 still matches the live work tree."""
        record = self.record(release_id)
        folder = self._dir(release_id)
        if record["status"] not in ("staged", "verified"):
            raise ReleaseError("Release cannot be verified from state " + record["status"])
        mismatches = []
        for change in record["changes"]:
            path = self.root / change["path"]
            try:
                if linked(path) or not path.is_file() or \
                        digest(path.read_bytes()) != change["original_sha256"]:
                    mismatches.append(change["path"])
            except OSError:
                mismatches.append(change["path"])
        if mismatches:
            record["status"] = "refused"
            record["stale"] = mismatches
            self._save(folder, record)
            self._append_journal("stale", release_id=release_id, files=mismatches)
            raise ReleaseError(
                "Concurrent owner modification detected for " + ", ".join(mismatches) +
                "; nothing was applied.")
        record["status"] = "verified"
        record["verified"] = round(self.clock(), 3)
        self._save(folder, record)
        self._append_journal("verified", release_id=release_id)
        return record

    # ------------------------------------------------------------------
    # stage 4: safety gate
    # ------------------------------------------------------------------
    def _gate(self, release_id):
        """Phase 1 Git Safety Gate, fail closed, never weakened."""
        try:
            state = self.git_gate.inspect()
        except Exception as error:
            record = self.record(release_id)
            record["status"] = "refused"
            record["refused"] = ["git_unavailable: " + str(error)[:140]]
            self._save(self._dir(release_id), record)
            self._append_journal("refused", release_id=release_id,
                                 reason=["git_unavailable"])
            raise ReleaseError(
                "Git Safety Gate could not verify the work tree; promotion refused.") from None
        if state["dirty"]:
            record = self.record(release_id)
            record["status"] = "refused"
            record["refused"] = ["dirty_git_tree"]
            record["dirty_paths"] = state["paths"][:10]
            self._save(self._dir(release_id), record)
            self._append_journal("refused", release_id=release_id, reason=["dirty_git_tree"],
                                 paths=state["paths"][:5])
            raise ReleaseError(
                "Git Safety Gate: the work tree is dirty; nothing is promoted and "
                "existing owner work is preserved.")
        return state

    # ------------------------------------------------------------------
    # stage 5: promote -> health check -> accept or rollback
    # ------------------------------------------------------------------
    def promote(self, release_id, *, approved=False):
        if approved is not True:
            raise ReleaseError("Explicit explicit-approval flag is required for promotion.")
        record = self.record(release_id)
        folder = self._dir(release_id)
        if record["status"] != "verified":
            raise ReleaseError("Release must be verified before promotion; state is "
                               + record["status"])
        if "test_evidence" not in record:
            raise ReleaseError("Release has no linked test evidence.")
        self._gate(release_id)
        self._recheck_staleness(record)
        snapshot = folder / "snapshot"
        if snapshot.exists():
            shutil.rmtree(snapshot, ignore_errors=True)
        snapshot.mkdir(parents=True)
        record["status"] = "activating"
        record["activated"] = round(self.clock(), 3)
        self._save(folder, record)
        self._append_journal("activating", release_id=release_id,
                             files=[c["path"] for c in record["changes"]])
        try:
            for change in record["changes"]:
                path = self.root / change["path"]
                original = path.read_bytes()
                if digest(original) != change["original_sha256"]:
                    raise ReleaseError("Live source changed during promotion for "
                                       + change["path"] + "; activation cancelled.")
            # snapshot affected files only, verified byte for byte, before any live write
            for change in record["changes"]:
                backup = snapshot / Path(change["path"]).name
                atomic_write(backup, (self.root / change["path"]).read_bytes())
                if digest(backup.read_bytes()) != change["original_sha256"]:
                    raise ReleaseError("Rollback snapshot failed integrity validation.")
            for change in record["changes"]:
                data = (folder / "candidate" / Path(change["path"]).name).read_bytes()
                atomic_write(self.root / change["path"], data)
        except Exception as error:
            record["status"] = "refused"
            record["refused"] = ["activation_aborted: " + str(error)[:140]]
            # Partial activation must never survive: attempt exact restore first.
            try:
                self._restore(folder, record, record["changes"])
                record["status"] = "rolled_back"
                record["rollback_reason"] = record["refused"][0]
            except ReleaseError:
                pass  # unverifiable snapshot stays as "refused" for manual review
            self._save(folder, record)
            self._append_journal("refused", release_id=release_id,
                                 reason=record["refused"])
            raise
        try:
            health = self.health(self.root)
        except Exception as error:
            health = {"healthy": False, "findings": [{"error": type(error).__name__,
                                                      "message": str(error)[:140]}]}
        record["health"] = {"healthy": bool(health.get("healthy")),
                            "findings": (health.get("findings") or [])[:6]}
        if not health.get("healthy"):
            self._restore(folder, record, record["changes"])
            record["status"] = "rolled_back"
            self._save(folder, record)
            self._append_journal("rolled_back", release_id=release_id,
                                 reason="post_activation_health_check_failed")
            return {**record, "outcome": "rolled_back"}
        record["status"] = "accepted"
        record["accepted"] = round(self.clock(), 3)
        self._save(folder, record)
        self._append_journal("accepted", release_id=release_id,
                             files=[c["path"] for c in record["changes"]],
                             candidate_sha256={c["path"]: c["candidate_sha256"]
                                               for c in record["changes"]})
        return {**record, "outcome": "accepted"}

    def _recheck_staleness(self, record):
        for change in record["changes"]:
            path = self.root / change["path"]
            if linked(path) or not path.is_file() or \
                    digest(path.read_bytes()) != change["original_sha256"]:
                write = self.record(record["release_id"])
                write["status"] = "refused"
                write["stale"] = [change["path"]]
                self._save(self._dir(record["release_id"]), write)
                self._append_journal("stale", release_id=record["release_id"],
                                     files=[change["path"]])
                raise ReleaseError("Concurrent modification detected during promotion for "
                                   + change["path"] + "; nothing was applied.")

    # ------------------------------------------------------------------
    # rollback and crash recovery
    # ------------------------------------------------------------------
    def _restore(self, folder, record, snapshots):
        """Exact restore of affected files only; preserve newer human edits."""
        for change in snapshots:
            backup = folder / "snapshot" / Path(change["path"]).name
            if backup.is_symlink() or not backup.is_file() or \
                    digest(backup.read_bytes()) != change["original_sha256"]:
                raise ReleaseError("Rollback snapshot missing or corrupt for "
                                   + change["path"] + "; retained for manual review.")
        for change in snapshots:
            relative = PurePosixPath(change["path"])
            target = self.root / relative
            current = target.read_bytes()
            if digest(current) not in (change["original_sha256"], change["candidate_sha256"]):
                raise ReleaseError(
                    "Recovery conflicts with newer edits to " + relative.as_posix() +
                    "; snapshot retained for review.")
            atomic_write(target, (folder / "snapshot" / relative.name).read_bytes())

    def rollback(self, release_id, *, reason="operator_requested"):
        record = self.record(release_id)
        folder = self._dir(release_id)
        if record["status"] not in ("accepted", "activating"):
            raise ReleaseError("Release is not active; state is " + record["status"])
        self._restore(folder, record, record["changes"])
        record["status"] = "rolled_back"
        record["rollback_reason"] = str(reason)[:200]
        record["rolled_back"] = round(self.clock(), 3)
        self._save(folder, record)
        self._append_journal("rolled_back", release_id=release_id, reason=str(reason)[:120])
        return {**record, "outcome": "rolled_back"}

    def recover(self):
        """Roll back every release found mid-activation (restart-safe)."""
        recovered = []
        if not self.releases_dir.is_dir():
            return recovered
        for folder in sorted(self.releases_dir.iterdir()):
            manifest = folder / "manifest.json"
            if not folder.is_dir() or manifest.is_symlink() or not manifest.is_file():
                continue
            try:
                record = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if record.get("status") not in APPLYING_STATUSES:
                continue
            try:
                self._restore(folder, record, record["changes"])
                record["status"] = "recovered"
                record["recovered"] = round(self.clock(), 3)
                self._save(folder, record)
                self._append_journal("recovered", release_id=record["release_id"])
                recovered.append(record["release_id"])
            except ReleaseError:
                # unreadable snapshot: leave for manual review, never touch more
                record["status"] = "refused"
                record["refused"] = ["recovery_blocked_snapshot_integrity"]
                self._save(folder, record)
        return recovered
