"""SPARK Autonomous Evolution Engine (SAEE) core.

This is the orchestration layer the master prompt calls for. It does NOT
reimplement repository analysis, source repair, skills or memory: those already
exist and are hardened (`spark_repo_upgrade`, `spark_maintenance`,
`spark_evolution`, `arkus_skill_forge`, `spark_intelligence`). SAEE composes them
behind one registry and one ledger so an upgrade request has a durable,
inspectable record and a single entry point.

Design constraints (mirrors the documented guardrails in
docs/intelligence-operations.md):

* No shell execution, no model-selected commands, no automatic deployment,
  merge, credential change or updater.
* Capability discovery is advisory: it maps a request to known capabilities and
  genuine gaps, then proposes a plan of existing approved actions.
* Every mutating step remains owned by the existing engine that stages it and
  requires the same explicit approvals. SAEE never widens authority; the only
  actions it performs itself are reads and appends to its own local ledger.

Storage lives beside the other workspace data:
``<workspace.skills.root.parent>/saee``.
"""
import ast
import json
import re
import secrets
import time
from pathlib import Path

from spark_maintenance import Maintenance, MaintenanceError, atomic_write, digest


LEDGER_KINDS = frozenset({
    "capability", "request", "attempt", "error_signature", "repair", "benchmark",
})

# The pipeline from the master prompt, in order. SAEE reports which stage an
# attempt has reached; it never skips a gate.
PIPELINE = (
    "request", "inspect", "plan", "risk_check", "isolate", "develop",
    "test", "security_check", "benchmark", "release_gate", "deploy",
    "verify", "monitor",
)

# Documented capability inventory seed. Each entry names an engine that is
# actually present in this repository and whether it is verified by tests.
# `verified` is conservative: it means an existing automated test exercises it,
# not that every path is safe. SAEE never claims runtime verification.
KNOWN_CAPABILITIES = (
    {"id": "repository_intelligence",
     "name": "Repository Intelligence Engine",
     "engine": "spark_repo_upgrade.RepositoryUpgrades",
     "summary": "Bounded, symlink-safe source sampling and reviewable upgrade proposals.",
     "verified": True, "gate": "analysis + staged change approval"},
    {"id": "repository_import",
     "name": "Isolated GitHub Repository Import",
     "engine": "spark_repo_import.import_evidence",
     "summary": "Shallow, code-execution-free GitHub clone with license reading and a dependency map.",
     "verified": True, "gate": "read-only evidence; reuse still analysis + approval"},
    {"id": "source_repair",
     "name": "Self-Diagnosis and Self-Healing",
     "engine": "spark_maintenance.Maintenance",
     "summary": "AST + regression validation, durable rollback journals, staged activation.",
     "verified": True, "gate": "candidate test + activation approval"},
    {"id": "code_generation",
     "name": "Bounded Code Generation",
     "engine": "spark_evolution.Evolution",
     "summary": "Model-generated complete-file replacements scoped to selected backend sources.",
     "verified": True, "gate": "staging + approval"},
    {"id": "calculation_skills",
     "name": "Declarative Calculation Skills",
     "engine": "arkus_skill_forge.SkillForge",
     "summary": "Versioned, tested numeric skills with activation and rollback.",
     "verified": True, "gate": "test + activation"},
    {"id": "instructional_skills",
     "name": "Instructional SKILL.md Import",
     "engine": "spark_intelligence.skills.InstructionalSkills",
     "summary": "Bounded frontmatter instruction import; grants no tools.",
     "verified": True, "gate": "validate + activation"},
    {"id": "prompt_improvement",
     "name": "Learning and Improvement Registry",
     "engine": "spark_intelligence.policy.Improvements",
     "summary": "Prompt/few-shot candidates scored on independent expected answers.",
     "verified": True, "gate": "benchmark + activation"},
    {"id": "agent_plans",
     "name": "Bounded Agent Plans and Scheduling",
     "engine": "spark_intelligence.runtime.Runtime",
     "summary": "Approval-bound local tool plans, checkpointed, scheduler off by default.",
     "verified": True, "gate": "plan approval; scheduler explicit"},
    {"id": "version_inspection",
     "name": "Version and Compatibility Inspection",
     "engine": "spark_intelligence.upgrades",
     "summary": "Read-only package/license visibility and pip check; installs nothing.",
     "verified": True, "gate": "read-only"},
    {"id": "local_memory",
     "name": "Project Memory and Retrieval",
     "engine": "spark_intelligence.memory.Memory",
     "summary": "Project-isolated FTS5 memory with citations; optional local embeddings.",
     "verified": True, "gate": "read/write within project"},
    {"id": "windows_file_organization",
     "name": "Windows File Organization Agent",
     "engine": "spark_file_organizer.FileOrganizer",
     "summary": "Read-only scan proposes moves; approved apply journals and undo reverses them.",
     "verified": True, "gate": "scan + approved plan hash; undo journalled"},
    {"id": "file_intelligence",
     "name": "File Intelligence (read-only)",
     "engine": "spark_file_intelligence.FileIntelligence",
     "summary": "Exact duplicate detection, large/old/temp inventory; changes nothing.",
     "verified": True, "gate": "read-only report"},
    {"id": "environmental_self_healing",
     "name": "Environmental Self-Diagnosis",
     "engine": "spark_self_healing.diagnose",
     "summary": "Read-only startup, dependency, runtime, connectivity and resource checks; bounded repair gate.",
     "verified": True, "gate": "read-only; repair still approval-gated"},
)

# Capability gaps the master prompt asks for that have no engine yet. SAEE
# reports these honestly rather than pretending they exist.
KNOWN_GAPS = (
    {"id": "automatic_deployment",
     "name": "Automatic Release and Rollback Pipeline",
     "reason": "Deliberately absent: docs/intelligence-operations.md rejects auto-merge/deploy/updater."},
    {"id": "weight_training",
     "name": "Model Weight Training / Optimizers",
     "reason": "DSPy/GEPA/ACE optimizers remain deferred; no research stack installed."},
    {"id": "self_optimization_profiler",
     "name": "Self-Optimization Profiler",
     "reason": "Only host vitals and read-only version inspection exist; no SPARK-owned process profiler."},
    {"id": "recursive_file_organization",
     "name": "Recursive / Scheduled File Organization",
     "reason": "Only single-directory, top-level, approval-gated moves exist; no recursion or scheduling."},
    {"id": "near_duplicate_detection",
     "name": "Near-Duplicate and Content Classification",
     "reason": "Only exact SHA-256 duplicates are detected; no fuzzy/semantic near-duplicate matching or content-based project classification."},
    {"id": "filesystem_natural_language_search",
     "name": "Natural-Language Filesystem Search",
     "reason": "NL search covers indexed documents and memories only; no NL query over raw filesystem metadata."},
)

_PROJECT = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Generic words that should never by themselves select a capability.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "your", "you", "add", "new",
    "use", "using", "make", "made", "get", "want", "need", "please", "can",
    "could", "would", "should", "into", "from", "about", "some", "any", "all",
    "local", "spark", "system", "systems", "engine", "engines", "tool", "tools",
    "capability", "capabilities", "feature", "features", "improve", "improving",
    "propose", "proposal", "support", "work", "works", "workspace", "project",
    "analyze", "analysis", "read", "review", "existing", "like", "more",
})


def _keyword_tokens(text):
    return {token for token in re.findall(r"[a-z0-9]+", str(text).lower())
            if len(token) > 2 and token not in _STOPWORDS}


class SAEEError(ValueError):
    pass


class AutonomousEvolutionEngine:
    """Registry + ledger + advisory planner over the existing engines.

    Read-only discovery is always available. It never stages, activates or
    deploys anything itself; those still go through the existing engines and
    their approval gates.
    """

    def __init__(self, workspace, evolution=None, maintenance=None, clock=time.time):
        self.workspace = workspace
        self.evolution = evolution
        self.clock = clock
        self.root = workspace.skills.root.parent / "saee"
        self.maintenance = maintenance or Maintenance(
            Path(__file__).resolve().parents[1], workspace.skills.root.parent)
        self.LEDGER_KINDS = LEDGER_KINDS

    # --- storage ---------------------------------------------------------
    def _project_dir(self, project):
        if not isinstance(project, str) or not _PROJECT.fullmatch(project):
            raise SAEEError("Use a valid project identifier.")
        folder = self.root / project
        if self.root.is_symlink() or folder.is_symlink():
            raise SAEEError("Linked SAEE storage is not allowed.")
        return folder

    def _file(self, project, kind, identity):
        if kind not in LEDGER_KINDS:
            raise SAEEError("Unknown ledger kind.")
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{24}", identity):
            raise SAEEError("Invalid ledger identifier.")
        return self._project_dir(project) / (kind + "-" + identity + ".json")

    def _append(self, project, kind, value):
        folder = self._project_dir(project)
        record = {"id": secrets.token_hex(12), "kind": kind, "project": project,
                  "created": self.clock(), **value}
        atomic_write(folder / (kind + "-" + record["id"] + ".json"),
                     json.dumps(record, indent=2, sort_keys=True).encode())
        return record

    def _list(self, project, kind, limit=200):
        folder = self._project_dir(project)
        if not folder.is_dir():
            return []
        files = sorted(folder.glob(kind + "-*.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
        results = []
        for path in files[:max(0, min(int(limit), 400))]:
            if path.is_symlink():
                continue
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return results

    # --- registry --------------------------------------------------------
    def registry(self, project):
        """The versioned capability inventory, including honest gaps."""
        self._project_dir(project)
        return {
            "capabilities": [dict(item) for item in KNOWN_CAPABILITIES],
            "gaps": [dict(item) for item in KNOWN_GAPS],
            "pipeline": list(PIPELINE),
            "measured": False,
            "note": ("Capability presence and test coverage are from the local "
                     "inventory; runtime behavior and security are not independently verified."),
        }

    def _repository_root(self):
        # spark_saee.py lives in <root>/backend, so the repo root is parents[1].
        return Path(__file__).resolve().parents[1]

    def _live_inventory(self):
        """Scan the real checkout so the registry reflects what is present.

        For every declared capability, confirm its engine module exists and
        locate a test that names it. Also collect the action keys other modules
        actually expose. Pure read-only; nothing is imported or executed.
        """
        root = self._repository_root()
        backend = root / "backend"
        tests = root / "tests"
        modules = {}
        if backend.is_dir() and not backend.is_symlink():
            for source in sorted(backend.glob("*.py")):
                if source.is_symlink():
                    continue
                modules[source.name] = source
            # Sub-packages (for example spark_intelligence) expose engines too:
            # register the package name and each of its modules.
            for package in sorted(p for p in backend.iterdir() if p.is_dir() and not p.is_symlink()):
                if (package / "__init__.py").is_file():
                    modules[package.name + ".py"] = package / "__init__.py"
                    for source in sorted(package.glob("*.py")):
                        if not source.is_symlink():
                            modules[package.name + "/" + source.name] = source
        test_names = set()
        if tests.is_dir() and not tests.is_symlink():
            test_names = {path.name for path in tests.glob("test_*.py") if not path.is_symlink()}

        capabilities = []
        for item in KNOWN_CAPABILITIES:
            engine = item["engine"]
            module_key = engine.replace(".", "/", 1) + ".py" if "." in engine else engine + ".py"
            # Accept both "spark_intelligence/memory.py" and the package form.
            candidates = [module_key]
            package_name = engine.split(".", 1)[0]
            candidates.append(package_name + ".py")
            source = next((modules.get(key) for key in candidates if key in modules), None)
            present = source is not None
            # Prefer a test naming the specific engine module/class (for example
            # "memory.Memory" or "skills.InstructionalSkills"); fall back to the
            # package name so coverage is still reported.
            probes = []
            if "." in engine:
                head, _, tail = engine.rpartition(".")
                if "." in head:
                    probes.append(head.rsplit(".", 1)[-1] + "." + tail)
                if len(tail) >= 6:
                    probes.append(tail)
            probes.append(package_name)
            test_file = None
            if present:
                for probe in probes:
                    for name in sorted(test_names):
                        text = (tests / name).read_text(encoding="utf-8", errors="replace")
                        if probe in text:
                            test_file = name
                            break
                    if test_file:
                        break
            capabilities.append({
                **item,
                "module_present": present,
                "test_file": test_file,
                "live": present,
            })

        action_sets = {}
        for name, source in modules.items():
            if source.stat().st_size > 200_000:
                continue
            try:
                tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"))
            except (SyntaxError, ValueError, OSError):
                continue
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                        and isinstance(node.targets[0], ast.Name) \
                        and (node.targets[0].id.endswith("_ACTIONS")
                             or node.targets[0].id == "ACTION_KEYS") \
                        and isinstance(node.value, ast.Dict):
                    keys = [key.value for key in node.value.keys
                            if isinstance(key, ast.Constant) and isinstance(key.value, str)]
                    if keys:
                        action_sets[name] = sorted(keys)
        return {"capabilities": capabilities, "action_sets": action_sets}

    def inventory(self, project):
        """Live capability inventory cross-checked against the real checkout."""
        self._project_dir(project)
        live = self._live_inventory()
        missing = [item["id"] for item in live["capabilities"] if not item["module_present"]]
        untested = [item["id"] for item in live["capabilities"]
                    if item["module_present"] and not item["test_file"]]
        return {
            "capabilities": live["capabilities"],
            "action_sets": live["action_sets"],
            "gaps": [dict(item) for item in KNOWN_GAPS],
            "missing_modules": missing,
            "untested": untested,
            "measured": True,
            "note": ("Presence and coverage are scanned from the local checkout; this is "
                     "not a security audit and does not prove runtime behavior."),
        }

    def discover(self, project, request):
        """Advisory capability discovery for a natural-language upgrade request.

        Matches the request against the known capability inventory and returns
        the genuine gaps, an assessed risk, and a plan whose steps reference
        existing engine actions. It executes nothing.
        """
        if not isinstance(request, str) or not 1 <= len(request.strip()) <= 2000:
            raise SAEEError("Describe the desired capability in 1-2000 characters.")
        request = request.strip()
        tokens = _keyword_tokens(request)
        scored = []
        for item in KNOWN_CAPABILITIES:
            strong = _keyword_tokens(item["name"] + " " + item["id"])
            weak = _keyword_tokens(item["summary"])
            score = 2 * len(tokens & strong) + len(tokens & weak)
            # Require at least one strong (name/id) hit: generic summary words
            # alone must not select a capability.
            if score and (tokens & strong):
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        matches = [{"id": item["id"], "name": item["name"], "engine": item["engine"],
                    "match_score": score, "gate": item["gate"]}
                   for score, item in scored[:4]]
        gaps = [dict(item) for item in KNOWN_GAPS
                if tokens & _keyword_tokens(item["name"] + " " + item["id"])]
        risk = self._risk(matches, gaps)
        plan = self._plan(matches, gaps)
        record = {
            "request": request,
            "matches": matches,
            "gaps": gaps,
            "risk": risk,
            "plan": plan,
            "stage": "plan",
            "executed": False,
            "note": ("Advisory only. Any code change still goes through the existing "
                     "staged engines and their explicit approvals."),
        }
        self._append(project, "request", record)
        for gap in gaps:
            self._append(project, "capability", {
                "capability": gap["id"], "state": "missing", "detail": gap["reason"]})
        return record

    def _risk(self, matches, gaps):
        if gaps and not matches:
            level = "high"
            reasons = ["Requested capability has no existing engine."]
        elif gaps:
            level = "medium"
            reasons = ["Partially covered; a real gap remains."]
        elif matches:
            level = "low"
            reasons = ["Map to an existing engine and its approval gate."]
        else:
            level = "medium"
            reasons = ["No existing engine matched; this needs a new design or a clearer request."]
        reasons.append("No deployment, merge or credential action is ever automatic.")
        return {"level": level, "reasons": reasons}

    def _plan(self, matches, gaps):
        steps = []
        if matches:
            steps.append({"stage": "inspect",
                          "action": "list_repository_analyses / read_repository_analysis",
                          "engine": matches[0]["engine"], "gate": "read-only"})
            steps.append({"stage": "develop",
                          "action": "analyze_repository -> stage_repository_upgrade",
                          "engine": "spark_repo_upgrade", "gate": "staged change approval"})
            steps.append({"stage": "test",
                          "action": "test_repair_candidate",
                          "engine": "spark_maintenance", "gate": "test approval"})
            steps.append({"stage": "release_gate",
                          "action": "activate_repair_candidate",
                          "engine": "spark_maintenance", "gate": "activation approval"})
        for gap in gaps:
            steps.append({"stage": "inspect",
                          "action": "design new subsystem: " + gap["id"],
                          "engine": "manual", "gate": "new design + safety tests required"})
        return steps

    # --- ledger ----------------------------------------------------------
    def record_attempt(self, project, request_id, stage, outcome, evidence=None):
        """Append one pipeline observation for an upgrade attempt."""
        if stage not in PIPELINE:
            raise SAEEError("Unknown pipeline stage.")
        if not isinstance(outcome, str) or not 1 <= len(outcome) <= 600:
            raise SAEEError("Outcome must be 1-600 characters.")
        return self._append(project, "attempt", {
            "request_id": request_id if isinstance(request_id, str) else None,
            "stage": stage, "outcome": outcome,
            "evidence": evidence if isinstance(evidence, dict) else {},
        })

    def record_error_signature(self, project, signature, repair=None, verified=False):
        """Store a verified error signature and any successful repair procedure."""
        if not isinstance(signature, str) or not 1 <= len(signature) <= 600:
            raise SAEEError("Error signature must be 1-600 characters.")
        dedup = digest(signature.encode())[:32]
        for existing in self._list(project, "error_signature", limit=400):
            if existing.get("dedup") == dedup and existing.get("signature") == signature:
                return existing
        return self._append(project, "error_signature", {
            "signature": signature, "dedup": dedup,
            "repair": repair if isinstance(repair, str) else None,
            "verified": bool(verified),
        })

    def record_repair(self, project, repair_id, action, result):
        if not isinstance(action, str) or not 1 <= len(action) <= 200:
            raise SAEEError("Repair action must be 1-200 characters.")
        return self._append(project, "repair", {
            "repair_id": repair_id if isinstance(repair_id, str) else None,
            "action": action, "result": result if isinstance(result, dict) else {},
        })

    def record_benchmark(self, project, name, before, after):
        """Store a before/after measurement; both values must be finite numbers."""
        def _finite(value):
            return isinstance(value, (int, float)) and not isinstance(value, bool) \
                and value == value and abs(value) != float("inf")
        if not _finite(before) or not _finite(after):
            raise SAEEError("Benchmark values must be finite numbers.")
        delta = after - before
        return self._append(project, "benchmark", {
            "name": str(name)[:120], "before": before, "after": after,
            "delta": delta, "improved": delta < 0,
        })

    def ledger(self, project, limit=200):
        """The full evolution ledger for a project, newest first per kind."""
        return {kind: self._list(project, kind, limit) for kind in sorted(LEDGER_KINDS)}

    def failures(self, project):
        """Error signatures that were not resolved by a verified repair."""
        return [item for item in self._list(project, "error_signature", 400)
                if not item.get("verified")]
