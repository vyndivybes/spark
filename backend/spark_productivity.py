"""Original SPARK local preferences, agenda, and durable reviewed routines."""
from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from spark_task_engine import Task, Step, State
from spark_cinematic_tools import get_system_status
from spark_desktop import launch_allowed_app, ALLOWED_APPS


class WorkbenchError(ValueError):
    pass


def text(value, limit=2000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise WorkbenchError(f"Text must contain 1–{limit} characters.")
    return value.strip()


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24,32}", value):
        raise WorkbenchError("Invalid item identifier.")
    return value


class Productivity:
    def __init__(self, data_dir, skills, launcher=None, clock=None):
        self.root = Path(data_dir).resolve() / "workbench"
        self.skills = skills
        self.launcher = launcher or launch_allowed_app
        self.clock = clock or time.time
        self.lock = threading.RLock()

    @contextmanager
    def _db(self, project):
        # The existing skill path validator enforces the same project namespace.
        self.skills._file(project)
        folder = self.root / project
        path = folder / "workspace.sqlite3"
        if any(p.is_symlink() for p in (self.root, folder, path)):
            raise WorkbenchError("Linked workbench storage is not allowed.")
        folder.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,kind TEXT NOT NULL,body TEXT NOT NULL)")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _all(self, db, kind):
        return [json.loads(row[0]) for row in db.execute("SELECT body FROM items WHERE kind=? ORDER BY rowid", (kind,))]

    def _put(self, db, kind, item):
        encoded = json.dumps(item)
        if len(encoded.encode()) > 100000:
            raise WorkbenchError("Workspace item exceeds its storage limit.")
        existing = db.execute("SELECT 1 FROM items WHERE id=? AND kind=?", (item["id"], kind)).fetchone()
        if not existing and db.execute("SELECT COUNT(*) FROM items WHERE kind=?", (kind,)).fetchone()[0] >= 100:
            raise WorkbenchError("Maximum 100 items per category in this project.")
        db.execute("INSERT OR REPLACE INTO items VALUES(?,?,?)", (item["id"], kind, encoded))

    def _get(self, db, kind, item_id):
        identity(item_id)
        row = db.execute("SELECT body FROM items WHERE id=? AND kind=?", (item_id, kind)).fetchone()
        if not row:
            raise WorkbenchError("Item not found in this project.")
        return json.loads(row[0])

    def snapshot(self, project):
        with self.lock, self._db(project) as db:
            return {kind: self._all(db, kind) for kind in ("preference", "agenda", "routine")}

    def preference(self, project, key, value):
        key, value = text(key, 80), text(value)
        with self.lock, self._db(project) as db:
            previous = next((p for p in self._all(db, "preference") if p["key"] == key), None)
            item = {"id": previous["id"] if previous else secrets.token_hex(12), "key": key, "value": value}
            self._put(db, "preference", item)
            return item

    def agenda(self, project, title, due, kind):
        title = text(title, 200)
        if kind not in ("reminder", "event"):
            raise WorkbenchError("Agenda kind must be reminder or event.")
        try:
            instant = datetime.fromisoformat(due.replace("Z", "+00:00"))
            if instant.tzinfo is None or not 2000 <= instant.year <= 2100:
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            raise WorkbenchError("Supply an ISO date and time with an explicit timezone.") from None
        item = {"id": secrets.token_hex(12), "title": title, "due": instant.astimezone(timezone.utc).isoformat(),
                "kind": kind, "done": False}
        with self.lock, self._db(project) as db:
            self._put(db, "agenda", item)
        return item

    def update_agenda(self, project, item_id, done):
        if type(done) is not bool:
            raise WorkbenchError("Agenda completion must be true or false.")
        with self.lock, self._db(project) as db:
            item = self._get(db, "agenda", item_id)
            item["done"] = done
            self._put(db, "agenda", item)
        return item

    def due(self, project):
        with self.lock, self._db(project) as db:
            return [item for item in self._all(db, "agenda") if not item["done"]
                    and datetime.fromisoformat(item["due"]).timestamp() <= self.clock()]

    def remove(self, project, kind, item_id):
        if kind not in ("preference", "agenda", "routine"):
            raise WorkbenchError("Invalid item category.")
        with self.lock, self._db(project) as db:
            self._get(db, kind, item_id)
            db.execute("DELETE FROM items WHERE id=? AND kind=?", (item_id, kind))
        return {"removed": item_id}

    @staticmethod
    def validate_steps(proposed):
        if not isinstance(proposed, list) or not 1 <= len(proposed) <= 12:
            raise WorkbenchError("Routines require 1–12 reviewed steps.")
        steps = []
        for candidate in proposed:
            if not isinstance(candidate, dict) or set(candidate) != {"action", "args"} or not isinstance(candidate["args"], dict):
                raise WorkbenchError("Each step requires action and args.")
            action, args = candidate["action"], candidate["args"]
            if action == "launch_desktop_app":
                valid = set(args) == {"app"} and args["app"] in ALLOWED_APPS
            elif action == "get_system_status":
                valid = not args
            elif action == "run_skill":
                valid = set(args) == {"name", "params"} and isinstance(args["name"], str) and isinstance(args["params"], dict)
            else:
                valid = False
            if not valid:
                raise WorkbenchError("Routine step is outside the approved action list.")
            steps.append(Step(action, dict(args)))
        return steps

    def create_routine(self, project, title, proposed):
        task = Task(text(title, 200), self.validate_steps(proposed))
        item = asdict(task)
        item["created"] = self.clock()
        with self.lock, self._db(project) as db:
            self._put(db, "routine", item)
        return item

    def advance(self, project, item_id, approved, expected_step):
        if type(approved) is not bool:
            raise WorkbenchError("Routine step approval must be explicit.")
        with self.lock, self._db(project) as db:
            item = self._get(db, "routine", item_id)
            if type(expected_step) is not int or expected_step != item["cursor"]:
                raise WorkbenchError("Routine advanced since this approval. Refresh and review its current step.")
            task = Task(item["description"], [Step(s["action"], s["args"], State(s["status"]), s["attempts"], s["result"]) for s in item["steps"]])
            task.id, task.status, task.cursor, task.audit = item["id"], State(item["status"]), item["cursor"], item["audit"]
            if task.status == State.RUNNING:
                # Never repeat an action whose process died before saving the result.
                task.status = task.current().status = State.FAILED
                task.audit.append("Interrupted action has unknown outcome; no automatic retry.")
            elif task.status not in (State.PENDING, State.AWAITING_APPROVAL):
                raise WorkbenchError("Routine is terminal. Create a new routine to run it again.")
            else:
                task.request_approval()
                if approved:
                    reservation = asdict(task)
                    reservation["status"] = "running"
                    reservation["steps"][task.cursor]["status"] = "running"
                    reservation["created"] = item["created"]
                    self._put(db, "routine", reservation)
                    db.commit()
                started = time.monotonic()
                def execute(action, args):
                    if action == "run_skill":
                        return self.skills.run(project, args["name"], args["params"])
                    if action == "get_system_status":
                        return get_system_status()
                    return self.launcher(args["app"])
                def verify(action, args, result):
                    return isinstance(result, dict) and (result.get("ok") is True if action == "launch_desktop_app" else
                                                        "result" in result if action == "run_skill" else result.get("service") == "SPARK Core")
                task.execute_approved(approved, execute, verify)
                task.audit.append(f"Elapsed {round((time.monotonic()-started)*1000)} ms")
            updated = {**asdict(task), "created": item["created"]}
            self._put(db, "routine", updated)
        return updated


def transform_text(value, operation):
    text(value, 50000)
    if operation == "json":
        try:
            result = json.dumps(json.loads(value), indent=2, ensure_ascii=False)
        except (ValueError, RecursionError):
            raise WorkbenchError("Clipboard text is not valid bounded JSON.") from None
    elif operation == "upper": result = value.upper()
    elif operation == "lower": result = value.lower()
    elif operation == "trim": result = "\n".join(line.strip() for line in value.splitlines())
    elif operation == "stats":
        return {"characters": len(value), "words": len(value.split()), "lines": len(value.splitlines())}
    else: raise WorkbenchError("Unsupported text operation.")
    return {"text": result}
