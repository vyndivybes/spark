"""Offline acceptance smoke: isolated D: workspace end to end (Phase 2).

Runs a throw-away fixture repository, an offline fake engine (mock
inference, no network, no paid APIs) and the production default isolated
base directory on D:. Promotions are kept gated mid-flight to prove the
dirty-tree hold, then promoted after gate recovery. The live SPARK
checkout is never touched; production autonomy stays paused.

The smoke cleans its own scratch and workspace copies afterward, but the
shared audit.jsonl history is retained on D: as commissioning evidence.
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from spark_auto_evolution import AutoEvolution
from spark_isolated_upgrade import IsolatedUpgradeManager, DEFAULT_BASE_DIRECTORY

sys.path.insert(0, str(Path(__file__).resolve().parent))
from isolated_upgrade_smoke_fakes import FakeEvolution, MutableGate, CLEAN, DIRTY

SCRATCH_BASE = Path(r"D:\SPARK-Evolution-Temp\smoke-20261024")
ORIGIN = "value=3\n"
EXPECTED = ORIGIN + "\n\ndef double(number):\n    return number * 2\n"

CANDIDATE_TESTS = "\n".join([
    "import sys",
    "import unittest",
    "from pathlib import Path",
    "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))",
    "import calculator as module",
    "",
    "class CalculatorCandidateTests(unittest.TestCase):",
    "    def test_value_is_preserved(self):",
    "        self.assertEqual(module.value, 3)",
    "",
    "    def test_double_behavior(self):",
    "        self.assertEqual(module.double(21), 42)",
])


def default_base_workspaces():
    base = Path(DEFAULT_BASE_DIRECTORY)
    if not base.is_dir():
        return set()
    return {directory.name for directory in base.iterdir() if directory.is_dir()}


def prune_previous_smoke_workspaces():
    """Remove this smoke's leftovers from earlier runs on the default base."""
    base_path = str(SCRATCH_BASE)
    removed = []
    for directory in Path(DEFAULT_BASE_DIRECTORY).glob("*/manifest.json"):
        try:
            manifest = json.loads(directory.parent.joinpath("manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(manifest.get("live_root", "")).startswith(base_path):
            shutil.rmtree(directory.parent, ignore_errors=True)
            removed.append(directory.parent.name)
    return removed


async def main():
    removed_before = prune_previous_smoke_workspaces()
    SCRATCH_BASE.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="spark-smoke-", dir=SCRATCH_BASE))
    repo = scratch / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "backend" / "calculator.py").write_text(ORIGIN, encoding="utf-8")
    (repo / "tests" / "test_spark_calculator.py").write_text(CANDIDATE_TESTS, encoding="utf-8")

    engine = FakeEvolution(repo)
    gate = MutableGate(DIRTY)  # start dirty: like the current live repository
    data = scratch / "data"
    manager = IsolatedUpgradeManager(engine, repo)  # no base_dir: the D: default
    time = [5_000_000]
    control = AutoEvolution(engine, data, clock=lambda: time[0],
                            git_gate=gate, isolated=manager)
    control.configure(enabled=True, allow_model_source=True)
    control.set_background_limits(interval_seconds=60, max_upgrades_per_day=0)
    names_before = default_base_workspaces()
    print("default isolated base:", manager.base, "(drive", manager.base.drive + ")")
    if removed_before:
        print("pruned earlier smoke workspaces:", removed_before)

    control.queue_goal("Improve calculator double behavior")
    time[0] += 61
    held = await control.run_once("general")
    assert held["status"] == "isolated_staged", held
    assert (repo / "backend" / "calculator.py").read_text(encoding="utf-8") == ORIGIN
    assert manager.held_count() == 1, manager.list_candidates()
    print("dirty hold:", held["status"], "candidate", held["candidate_id"][:8])

    gate.state = CLEAN
    control.queue_goal("Improve calculator reliability")
    time[0] += 61
    promoted = await control.run_once("general")
    assert promoted["status"] == "applied", promoted
    assert (repo / "backend" / "calculator.py").read_text(encoding="utf-8") == EXPECTED
    statuses = [record["status"] for record in manager.list_candidates()]
    assert statuses == ["promoted", "tested"], statuses
    print("promotion:", promoted["status"], "candidates:", statuses)

    # A staged duplicate of the same target is now stale against the live
    # tree: the concurrent-modification guard keeps it in isolation.
    time[0] += 61
    second = await control.run_once("general")
    statuses = [record["status"] for record in manager.list_candidates()]
    assert statuses == ["promoted", "stale"], statuses
    assert (repo / "backend" / "calculator.py").read_text(encoding="utf-8") == EXPECTED
    print("stale duplicate guard:", second["status"], "candidates:", statuses)
    print("audit entries:", len(manager.history()))

    detached = AutoEvolution(None, data)
    detached.emergency_stop()
    status = detached.status()
    assert not status["enabled"] and not status["engine_attached"], status
    print("detached emergency stop: ok (engine_attached=%s)" % status["engine_attached"])
    print("SMOKE PASS")

    # clean the smoke's scratch and its default-base workspaces; the shared
    # audit.jsonl history remains on D: as evidence.
    shutil.rmtree(scratch, ignore_errors=True)
    for name in default_base_workspaces() - names_before:
        shutil.rmtree(Path(DEFAULT_BASE_DIRECTORY) / name, ignore_errors=True)
    shutil.rmtree(SCRATCH_BASE, ignore_errors=True)
    surviving = [record["status"] for record in manager.list_candidates()]
    print("post-cleanup audit entries:", len(manager.history()), "surviving candidates:", surviving)


if __name__ == "__main__":
    asyncio.run(main())
