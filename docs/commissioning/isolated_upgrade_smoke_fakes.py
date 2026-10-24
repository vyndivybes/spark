"""Offline fakes for the Phase 2 isolated-upgrade acceptance smoke."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


class FakeSkills:
    def _file(self, project):
        if project != "general":
            raise ValueError("Unknown project")


class FakeMaintenance:
    def __init__(self, root):
        self.root = root
        self.healthy = True

    def detect(self):
        return {"healthy": self.healthy, "findings": []}


class FakeRea:
    async def request(self, action, payload):
        return [{"name": "inspect", "description": "read-only"}]


class FakeSaee:
    def record_attempt(self, *args, **kwargs):
        return None


class FakeEvolution:
    def __init__(self, root):
        self.maintenance = FakeMaintenance(root)
        self.workspace = type("Widget", (), {"skills": FakeSkills()})()
        self.rea = FakeRea()
        self.saee = FakeSaee()
        self.actions = []
        self.improvement = "\n\ndef double(number):\n    return number * 2\n"
        self.staged = {}
        self.backups = {}
        self.stage_counter = 0

    async def execute(self, action, project, payload):
        self.actions.append((action, payload))
        if action == "analyze_repository":
            return {"id": "b" * 24, "opportunities": [
                {"spark_paths": ["backend/calculator.py"],
                 "verification": "calculator double behavior test"}]}
        if action == "stage_repository_upgrade":
            source = self.maintenance.root / "backend" / "calculator.py"
            change = {"path": "backend/calculator.py",
                      "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                      "content": source.read_text(encoding="utf-8") + self.improvement}
            record = {"id": hashlib.sha256(
                          (change["content"] + str(self.stage_counter)).encode()).hexdigest()[:24],
                      "status": "staged", "changes": [change]}
            self.stage_counter += 1
            self.staged[record["id"]] = record
            return record
        if action == "test_repair_candidate":
            return {"id": payload["id"], "status": "tested"}
        if action == "activate_repair_candidate":
            record = self.staged[payload["id"]]
            for change in record["changes"]:
                target = self.maintenance.root / change["path"]
                self.backups[change["path"]] = target.read_bytes()
                target.write_text(change["content"], encoding="utf-8")
            return {"id": payload["id"], "status": "applied"}
        if action == "rollback_repair":
            for relative, data in list(self.backups.items()):
                (self.maintenance.root / relative).write_bytes(data)
            self.backups.clear()
            return {"status": "rolled_back"}
        raise AssertionError(action)


class MutableGate:
    def __init__(self, c_state):
        self.state = c_state

    def inspect(self):
        return self.state


CLEAN = {"dirty": False, "paths": []}
DIRTY = {"dirty": True, "paths": ["notes.txt"]}
