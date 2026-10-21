"""Environmental self-diagnosis and bounded-repair gate (stdlib only, read-only).

The §3E "self-diagnosis and self-healing" items that are *not* about source-code
repair the engine writes itself. This module looks at the running environment and
reports honestly:

* startup failures — required top-level modules missing or unimportable
* dependency availability — declared optional/platform imports that are absent
* API/tool connectivity — DNS/TCP reachability of a small fixed provider set
* runtime failures — Python version floor and stdlib features the code assumes
* resource exhaustion — RAM/disk headroom relative to configurable thresholds

It is diagnosis-only: it never installs, deletes, restarts or edits anything.
Repair still flows through the maintenance/repo approval gates. Connectivity
probing is deliberately opt-in via a real probe function so tests never touch the
network.

`RepairGate` implements §3E's "never repeatedly execute the same failing repair
without new evidence": identical (signature, evidence) attempts are refused; a
changed evidence digest is new evidence and is allowed.
"""
import ast
import importlib.util
import shutil
import socket
import sys
from pathlib import Path

from spark_maintenance import digest


class SelfHealingError(ValueError):
    pass


# Modules SPARK core is expected to import. Missing any is a startup failure.
REQUIRED_MODULES = (
    "spark_maintenance", "spark_evolution", "spark_saee", "spark_workspace",
    "spark_groq", "spark",
)

# Optional/platform integrations: absent is a warning, not a failure.
OPTIONAL_MODULES = (
    "croniter", "psutil", "faiss", "sentence_transformers", "dspy", "gepa",
)

# Provider hosts for connectivity checks. Fixed, tiny, no ports invented.
PROVIDER_HOSTS = (
    ("groq", "api.groq.com", 443),
    ("gemini", "generativelanguage.googleapis.com", 443),
    ("github", "github.com", 443),
)

MIN_PYTHON = (3, 9)
DEFAULT_RAM_FLOOR_GB = 0.5
DEFAULT_DISK_FLOOR_GB = 1.0


def _module_present(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def check_startup(backend_dir):
    """Required backend modules that exist on disk and parse. Missing ones start-fail."""
    backend = Path(backend_dir)
    findings = []
    for name in REQUIRED_MODULES:
        source = backend / (name + ".py")
        package = backend / name / "__init__.py"
        if not source.is_file() and not package.is_file():
            findings.append({"module": name, "issue": "missing_module"})
            continue
        try:
            text = (source if source.is_file() else package).read_text(encoding="utf-8-sig")
            ast.parse(text, filename=name)
        except (OSError, SyntaxError) as error:
            findings.append({"module": name, "issue": "unparseable",
                             "detail": type(error).__name__})
    return {"ok": not findings, "findings": findings}


def check_dependencies(modules=None):
    """Report absent optional modules. Never imports them (find_spec only)."""
    names = OPTIONAL_MODULES if modules is None else tuple(modules)
    present, absent = [], []
    for name in names:
        (present if _module_present(name) else absent).append(name)
    return {"ok": True, "present": sorted(present), "absent": sorted(absent),
            "note": "Absent optional modules degrade features; they are not installed automatically."}


def check_runtime():
    """Python version floor and the specific stdlib features the code relies on."""
    findings = []
    if sys.version_info < MIN_PYTHON:
        findings.append({"issue": "python_too_old",
                         "detail": ".".join(map(str, sys.version_info[:3]))})
    # Features used by the safety-critical modules.
    if not hasattr(Path("."), "is_relative_to"):
        findings.append({"issue": "missing_path_is_relative_to"})
    if not callable(getattr(ast, "parse", None)):
        findings.append({"issue": "missing_ast_parse"})
    return {"ok": not findings, "python": ".".join(map(str, sys.version_info[:3])),
            "findings": findings}


def check_resources(*, vitals=None, ram_floor_gb=None, disk_floor_gb=None):
    """RAM/disk headroom from host vitals. Low headroom is a warning, not an error."""
    ram_floor = DEFAULT_RAM_FLOOR_GB if ram_floor_gb is None else float(ram_floor_gb)
    disk_floor = DEFAULT_DISK_FLOOR_GB if disk_floor_gb is None else float(disk_floor_gb)
    if vitals is None:
        try:
            from spark_host_vitals import collect_host_vitals
            vitals = collect_host_vitals()
        except Exception:
            vitals = {}
    findings = []
    ram = vitals.get("ram_available_gb")
    if isinstance(ram, (int, float)) and ram < ram_floor:
        findings.append({"resource": "ram", "available_gb": round(float(ram), 3),
                         "floor_gb": ram_floor, "issue": "low_memory"})
    disk = vitals.get("disk_free_gb")
    if isinstance(disk, (int, float)) and disk < disk_floor:
        findings.append({"resource": "disk", "free_gb": round(float(disk), 3),
                         "floor_gb": disk_floor, "issue": "low_disk"})
    return {"ok": not findings, "findings": findings,
            "ram_available_gb": ram, "disk_free_gb": disk}


def check_connectivity(*, probe=None, hosts=None):
    """Opt-in TCP reachability. `probe` is injected so tests never hit the network."""
    targets = PROVIDER_HOSTS if hosts is None else tuple(hosts)
    if probe is None:
        return {"ok": None, "checked": [],
                "note": "Connectivity probe not requested; pass a probe to enable it."}
    results = []
    for name, host, port in targets:
        try:
            reachable = bool(probe(host, port))
        except Exception:
            reachable = False
        results.append({"name": name, "reachable": reachable})
    return {"ok": all(item["reachable"] for item in results), "checked": results}


def diagnose(*, backend_dir=None, vitals=None, probe=None, deep=False):
    """Read-only environmental snapshot. `deep=True` enables the TCP probe."""
    backend = Path(backend_dir) if backend_dir else Path(__file__).resolve().parent
    startup = check_startup(backend)
    dependencies = check_dependencies()
    runtime = check_runtime()
    resources = check_resources(vitals=vitals)
    connectivity = check_connectivity(probe=probe if deep else None)
    healthy = startup["ok"] and runtime["ok"] and resources["ok"]
    return {
        "healthy": healthy,
        "startup": startup,
        "dependencies": dependencies,
        "runtime": runtime,
        "resources": resources,
        "connectivity": connectivity,
        "note": "Environmental diagnosis only; no repair is performed here.",
    }


class RepairGate:
    """Refuse an identical repair retry unless there is new evidence (§3E).

    State is supplied by the caller (the SAEE ledger), so this class is pure and
    testable. `attempts` is a list of {"signature", "evidence"} dicts already
    recorded. A retry is allowed only when the evidence digest changes.
    """

    def __init__(self, attempts=None):
        self.attempts = list(attempts or [])

    @staticmethod
    def _evidence_digest(evidence):
        return digest(repr(sorted((evidence or {}).items())).encode())

    def allow(self, signature, evidence=None):
        if not isinstance(signature, str) or not signature.strip():
            raise SelfHealingError("Repair signature is required.")
        new = self._evidence_digest(evidence)
        for attempt in self.attempts:
            if attempt.get("signature") == signature and \
                    attempt.get("evidence") == new:
                return {"allowed": False, "reason": "identical_repair_without_new_evidence"}
        self.attempts.append({"signature": signature, "evidence": new})
        return {"allowed": True, "reason": "new_attempt"}

    def record(self, signature, evidence=None):
        """Commit an attempt without a pre-check (used after an approved repair)."""
        if not isinstance(signature, str) or not signature.strip():
            raise SelfHealingError("Repair signature is required.")
        self.attempts.append({"signature": signature,
                              "evidence": self._evidence_digest(evidence)})
        return self.attempts[-1]

    def signatures(self):
        seen = []
        for attempt in self.attempts:
            if attempt.get("signature") not in seen:
                seen.append(attempt.get("signature"))
        return seen

    def repeated_failures(self):
        """Signatures attempted more than once (candidates for escalation)."""
        counts = {}
        for attempt in self.attempts:
            counts[attempt.get("signature")] = counts.get(attempt.get("signature"), 0) + 1
        return sorted(name for name, count in counts.items() if count > 1)


def disk_forecast(free_gb, used_gb_per_day, *, horizon_days=30):
    """Project free disk space at a constant daily growth. Pure arithmetic."""
    for value in (free_gb, used_gb_per_day, horizon_days):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SelfHealingError("Forecast inputs must be numbers.")
    projected = free_gb - used_gb_per_day * horizon_days
    days_to_empty = None
    if used_gb_per_day > 0:
        days_to_empty = max(0.0, free_gb / used_gb_per_day)
    return {
        "free_gb": round(float(free_gb), 3),
        "used_gb_per_day": float(used_gb_per_day),
        "horizon_days": horizon_days,
        "projected_free_gb": round(float(projected), 3),
        "days_to_empty": None if days_to_empty is None else round(days_to_empty, 1),
        "warning": projected < 0 or (days_to_empty is not None and days_to_empty < horizon_days),
    }
