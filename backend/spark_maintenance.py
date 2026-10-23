"""Bounded source repair with staged validation and durable rollback journals."""
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading


class MaintenanceError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with scratch.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
    finally:
        scratch.unlink(missing_ok=True)


class Maintenance:
    def __init__(self, repository, data_dir, validator=None):
        self.root = Path(repository).resolve()
        self.backups = Path(data_dir).resolve() / "maintenance"
        self.lock = threading.RLock()
        self.validator = validator or self._validate

    def _target(self, relative):
        if not isinstance(relative, str) or "\\" in relative:
            raise MaintenanceError("Use a relative backend Python source path.")
        path = self.root / relative
        if (Path(relative).is_absolute() or len(Path(relative).parts) != 2
                or Path(relative).parts[0] != "backend" or path.suffix != ".py"
                or not path.is_file() or path.is_symlink() or path.parent.is_symlink()
                or not path.resolve().is_relative_to(self.root)):
            raise MaintenanceError("Only existing backend Python source files can be repaired.")
        if path.name in {"spark_python_tools.py", "spark_code_skills.py", "spark_maintenance.py", "spark_rea.py", "server.py", "spark_evolution.py", "spark_repo_upgrade.py", "spark_auto_evolution.py", "spark_saee.py", "spark_security_scan.py", "spark_workspace_auth.py"}:
            raise MaintenanceError("Recovery and authorization code requires a reviewed manual upgrade.")
        return path

    def _validate(self, root):
        try:
            timeout=int(os.environ.get('SPARK_REPAIR_TEST_TIMEOUT','180'))
            if not 60<=timeout<=600:raise ValueError()
        except ValueError:
            raise MaintenanceError('SPARK_REPAIR_TEST_TIMEOUT must be 60–600 seconds.') from None
        for source in (root / "backend").glob("*.py"):
            ast.parse(source.read_text(encoding="utf-8-sig"), filename=source.name)
        self._security_check(root)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_spark*.py"],
            cwd=root, capture_output=True, timeout=timeout, text=True, encoding="utf-8", errors="replace",
            env={**{key:value for key,value in os.environ.items() if key.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','PATHEXT','LOCALAPPDATA','APPDATA','USERPROFILE'}},
                 "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8":"1"})
        if result.returncode:
            raise MaintenanceError("Regression suite failed; candidate was not retained.")

    def _security_check(self, root):
        # Heuristic secret scan over every backend source. A candidate that would
        # introduce a credential never reaches the release gate. Not a proof of
        # absence; see spark_security_scan.
        from spark_security_scan import scan_secrets
        for source in (root / "backend").glob("*.py"):
            if source.is_symlink():
                continue
            findings = scan_secrets(source.read_text(encoding="utf-8-sig"), "backend/" + source.name)
            if findings:
                raise MaintenanceError(
                    "Security check failed: a possible secret was found in " + source.name + ".")

    def detect(self):
        findings = []
        for source in (self.root / "backend").glob("*.py"):
            try:
                ast.parse(source.read_text(encoding="utf-8-sig"), filename=source.name)
            except SyntaxError as error:
                findings.append({"path": "backend/" + source.name, "line": error.lineno,
                                 "error": error.msg})
        if not findings:
            try:
                self.validator(self.root)
            except Exception as error:
                findings.append({"error": type(error).__name__, "message": "Regression validation failed."})
        return {"healthy": not findings, "findings": findings}

    def _journal(self, folder, record):
        atomic_write(folder / "journal.json", json.dumps(record, indent=2).encode())

    def recover(self):
        with self.lock:
            recovered = []
            for journal in sorted(self.backups.glob("*/journal.json")):
                record = json.loads(journal.read_text(encoding="utf-8"))
                if record["status"] == "applying":
                    self._rollback(journal.parent, record)
                    recovered.append(journal.parent.name)
            return recovered

    def history(self):
        with self.lock:
            return [json.loads(path.read_text(encoding="utf-8"))
                    for path in sorted(self.backups.glob("*/journal.json"))]

    def _candidate_path(self, identity):
        if not isinstance(identity,str) or len(identity)!=24 or any(c not in '0123456789abcdef' for c in identity):
            raise MaintenanceError('Invalid candidate identifier.')
        path=self.backups/'candidates'/(identity+'.json')
        if path.is_symlink() or path.parent.is_symlink():
            raise MaintenanceError('Linked candidate storage is prohibited.')
        return path

    def stage(self, changes, *, provenance=None):
        if not isinstance(changes,list) or not 1<=len(changes)<=4:
            raise MaintenanceError('Select one to four replacements.')
        seen=set()
        for change in changes:
            if not isinstance(change,dict) or set(change)!={'path','content','sha256'}:
                raise MaintenanceError('Invalid replacement fields.')
            path=self._target(change['path'])
            if path in seen or digest(path.read_bytes())!=change['sha256']:
                raise MaintenanceError('Duplicate or stale source replacement.')
            seen.add(path)
            if not isinstance(change['content'],str) or len(change['content'].encode())>65536:
                raise MaintenanceError('Oversized source replacement.')
            try:
                ast.parse(change['content'])
            except SyntaxError:
                raise MaintenanceError('Candidate has invalid Python syntax.') from None
        record={'id':secrets.token_hex(12),'status':'staged','changes':changes}
        if provenance is not None:
            record['provenance'] = provenance
        atomic_write(self._candidate_path(record['id']),json.dumps(record).encode())
        return record

    def candidates(self):
        return [json.loads(path.read_text(encoding='utf-8')) for path in sorted((self.backups/'candidates').glob('*.json')) if not path.is_symlink()]

    def test_candidate(self, identity, *, approved=False):
        if approved is not True:
            raise MaintenanceError('Approve local execution of candidate regression tests first.')
        path=self._candidate_path(identity)
        with self.lock:
            record=json.loads(path.read_text(encoding='utf-8'))
            if record['status'] not in ('staged','tested','rejected'):
                raise MaintenanceError('Candidate is no longer staged.')
            try:
                self.apply(record['changes'],validate_only=True)
                record['status']='tested'
            except Exception:
                record['status']='rejected'
                atomic_write(path,json.dumps(record).encode())
                raise
            atomic_write(path,json.dumps(record).encode())
            return record

    def activate_candidate(self, identity, *, approved=False):
        if approved is not True:
            raise MaintenanceError('Explicit production activation approval is required.')
        path=self._candidate_path(identity)
        with self.lock:
            record=json.loads(path.read_text(encoding='utf-8'))
            if record['status']!='tested':
                raise MaintenanceError('Candidate must pass testing before activation.')
            result=self.apply(record['changes'])
            record.update(status='activated',repair_id=result['id'])
            atomic_write(path,json.dumps(record).encode())
            return result

    def _rollback(self, folder, record):
        # Check every file before restoring any. Preserve subsequent human edits.
        for entry in record["files"]:
            target = self._target(entry["path"])
            current = digest(target.read_bytes())
            if current not in (entry["before"], entry["after"]):
                raise MaintenanceError("Recovery conflicts with newer edits; backup retained for review.")
            backup = folder / (Path(entry["path"]).name + ".bak")
            if backup.is_symlink() or digest(backup.read_bytes()) != entry["before"]:
                raise MaintenanceError("Recovery backup failed integrity validation.")
        for entry in record["files"]:
            atomic_write(self._target(entry["path"]), (folder / (Path(entry["path"]).name + ".bak")).read_bytes())
        record["status"] = "rolled_back"
        self._journal(folder, record)

    def rollback(self, identity):
        if not isinstance(identity, str) or len(identity) != 24 or any(c not in "0123456789abcdef" for c in identity):
            raise MaintenanceError("Invalid repair identifier.")
        with self.lock:
            folder = self.backups / identity
            record = json.loads((folder / "journal.json").read_text(encoding="utf-8"))
            if record["status"] not in ("applied", "applying"):
                raise MaintenanceError("Repair is not active.")
            self._rollback(folder, record)
            return {"id": identity, "status": "rolled_back", "restart_required": True}

    def apply(self, changes, *, validate_only=False):
        if not isinstance(changes, list) or not 1 <= len(changes) <= 4:
            raise MaintenanceError("Repair must contain one to four source replacements.")
        with self.lock:
            self.recover()
            originals, replacements = {}, {}
            for change in changes:
                if not isinstance(change, dict) or set(change) != {"path", "content", "sha256"}:
                    raise MaintenanceError("Each replacement needs path, content and original sha256.")
                path = self._target(change["path"])
                content = change["content"]
                if not isinstance(content, str) or len(content.encode()) > 65536 or path in originals:
                    raise MaintenanceError("Duplicate or oversized source replacement.")
                originals[path] = path.read_bytes()
                if digest(originals[path]) != change["sha256"]:
                    raise MaintenanceError("Source changed since diagnosis; regenerate the repair.")
                replacements[path] = content.encode()
            with tempfile.TemporaryDirectory(prefix="spark-repair-") as directory:
                stage = Path(directory)
                shutil.copytree(self.root / "backend", stage / "backend", ignore=shutil.ignore_patterns(".env", "*.bak", "__pycache__", "settings.json"))
                shutil.copytree(self.root / "tests", stage / "tests", ignore=shutil.ignore_patterns("__pycache__"))
                if (self.root/'package.json').is_file():shutil.copy2(self.root/'package.json',stage/'package.json')
                for source in (self.root / "scripts").glob("*.py"):
                    destination = stage / "scripts" / source.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                for source in (self.root / "vendor").rglob("*.py"):
                    if any(part in {"node_modules", ".git", ".venv", "__pycache__"} for part in source.parts):
                        continue
                    destination = stage / source.relative_to(self.root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                for source in (self.root/'vendor').glob('*/sample-notes/**/*.md'):
                    destination=stage/source.relative_to(self.root)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,destination)
                for path, content in replacements.items():
                    (stage / path.relative_to(self.root)).write_bytes(content)
                self.validator(stage)
            if validate_only:
                return {'status':'tested'}
            identity = secrets.token_hex(12)
            folder = self.backups / identity
            record = {"id": identity, "status": "applying", "files": []}
            for path, original in originals.items():
                if path.read_bytes() != original:
                    raise MaintenanceError("Source changed during validation; repair cancelled.")
                atomic_write(folder / (path.name + ".bak"), original)
                record["files"].append({"path": path.relative_to(self.root).as_posix(),
                                        "before": digest(original), "after": digest(replacements[path])})
            self._journal(folder, record)
            try:
                for path, content in replacements.items():
                    atomic_write(path, content)
                self.validator(self.root)
                record["status"] = "applied"
                self._journal(folder, record)
            except BaseException:
                self._rollback(folder, record)
                raise
            return {"id": identity, "status": "applied", "restart_required": True}
