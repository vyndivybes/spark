"""Bounded Windows file organization: preview first, approve, move, undo.

This is the "Windows File Organization Agent" the master prompt asks for, built
to the same safety standard as the rest of the workspace:

* Nothing moves during scanning. A scan only proposes moves for a single
  directory (never recursive by default), grouping top-level files into
  category folders.
* A move happens only for an exact, approved plan hash, one directory at a
  time, with a durable journal written before the first move so an interrupted
  or failed run can be rolled back.
* Every move is reversible: the journal records the exact source and
  destination, and undo refuses to clobber a path that changed after the move.
* No deletion, no recursion, no shell. Files are only ever renamed within the
  same directory tree the user named.
"""
import json
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path

from spark_maintenance import atomic_write, digest


class FileOrganizerError(ValueError):
    pass


FILE_ORGANIZER_ACTIONS = {
    "organize_scan": {"directory"},
    "organize_apply": {"id", "plan_hash", "approved"},
    "organize_undo": {"id", "approved"},
    "organize_history": set(),
}


# Extension -> category folder. Unknown extensions fall back to "_Others".
CATEGORIES = {
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".xls",
                  ".xlsx", ".csv", ".ppt", ".pptx", ".pages", ".numbers"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tif",
               ".tiff", ".heic", ".raw"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".flv", ".m4v"},
    "Archives": {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Installers": {".exe", ".msi", ".msix", ".appx", ".dmg"},
    "Code": {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".cjs", ".mjs", ".html",
             ".css", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb",
             ".sh", ".ps1", ".yml", ".yaml", ".toml", ".sql"},
}
FALLBACK = "_Others"

MAX_FILES = 2000


def _category(name):
    extension = Path(name).suffix.lower()
    for folder, extensions in CATEGORIES.items():
        if extension in extensions:
            return folder
    return FALLBACK


class FileOrganizer:
    def __init__(self, data_dir, root=None):
        self.root = Path(data_dir).resolve() / "file-organizer"
        self._allowed_root = Path(root).resolve() if root else None
        self.lock = threading.RLock()

    # --- guards ----------------------------------------------------------
    def _directory(self, value):
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise FileOrganizerError("Supply a directory path.")
        path = Path(os.path.expandvars(value)).expanduser()
        if not path.is_absolute():
            raise FileOrganizerError("Use an absolute directory path.")
        path = path.resolve()
        if self._allowed_root is not None and not path.is_relative_to(self._allowed_root):
            raise FileOrganizerError("That directory is outside the allowed root.")
        if path.is_symlink() or not path.is_dir():
            raise FileOrganizerError("That is not an existing, non-linked directory.")
        # Refuse obviously dangerous targets.
        if path == path.anchor or path == Path.home():
            raise FileOrganizerError("Refusing to organize a whole drive or the home folder.")
        return path

    def _plan_file(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{24}", identity):
            raise FileOrganizerError("Invalid plan identifier.")
        return self.root / (identity + ".json")

    def _journal_dir(self, identity):
        return self.root / ("run-" + identity)

    # --- scanning (read-only) -------------------------------------------
    def scan(self, directory):
        """Propose moves for the top-level files of one directory. Moves nothing."""
        folder = self._directory(directory)
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
        except OSError as error:
            raise FileOrganizerError("Could not read that directory: " + str(error)[:120]) from None
        moves = []
        skipped = []
        for entry in entries:
            if len(moves) >= MAX_FILES:
                skipped.append({"name": entry.name, "reason": "limit reached"})
                continue
            if entry.is_symlink() or not entry.is_file():
                skipped.append({"name": entry.name, "reason": "not a plain file"})
                continue
            category = _category(entry.name)
            if entry.parent.name == category:
                continue
            destination = folder / category / entry.name
            if destination.exists():
                skipped.append({"name": entry.name, "reason": "a file of that name already exists in the target folder"})
                continue
            moves.append({"name": entry.name, "from": str(entry), "to": str(destination),
                          "category": category})
        plan = {
            "id": secrets.token_hex(12),
            "directory": str(folder),
            "created": time.time(),
            "moves": moves,
            "skipped": skipped,
            "state": "proposed",
        }
        plan["plan_hash"] = digest(json.dumps(
            {"directory": plan["directory"], "moves": moves}, sort_keys=True).encode())
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write(self._plan_file(plan["id"]),
                     json.dumps(plan, indent=2, sort_keys=True).encode())
        return plan

    # --- apply (approved, journalled, reversible) ------------------------
    def apply(self, identity, plan_hash, approved):
        if approved is not True or not isinstance(plan_hash, str):
            raise FileOrganizerError("Approve the exact proposed plan.")
        path = self._plan_file(identity)
        if path.is_symlink() or not path.is_file():
            raise FileOrganizerError("Unknown organization plan.")
        with self.lock:
            plan = json.loads(path.read_text(encoding="utf-8"))
            if plan_hash != plan["plan_hash"]:
                raise FileOrganizerError("The plan changed since it was reviewed.")
            if plan["state"] == "applied":
                return plan
            if plan["state"] != "proposed":
                raise FileOrganizerError("This plan is not ready to apply.")
            journal = {"id": plan["id"], "directory": plan["directory"],
                       "created": time.time(), "state": "applying", "moved": []}
            journal_file = self._journal_dir(plan["id"]) / "journal.json"
            atomic_write(journal_file, json.dumps(journal).encode())
            try:
                for move in plan["moves"]:
                    source = Path(move["from"])
                    destination = Path(move["to"])
                    # Re-check at apply time: the world may have changed.
                    if source.is_symlink() or not source.is_file():
                        raise FileOrganizerError("Source is gone or changed: " + source.name)
                    if destination.exists():
                        raise FileOrganizerError("Target now exists: " + destination.name)
                    if source.parent != Path(plan["directory"]):
                        raise FileOrganizerError("Source escaped the planned directory.")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
                    journal["moved"].append({"from": str(source), "to": str(destination)})
                    atomic_write(journal_file, json.dumps(journal).encode())
            except (OSError, FileOrganizerError) as error:
                self._rollback(journal, journal_file)
                plan["state"] = "rolled_back"
                plan["error"] = str(error)[:200]
                atomic_write(path, json.dumps(plan, indent=2, sort_keys=True).encode())
                raise FileOrganizerError("Move failed and was rolled back: " + str(error)[:160]) from None
            journal["state"] = "applied"
            atomic_write(journal_file, json.dumps(journal).encode())
            plan["state"] = "applied"
            plan["applied"] = time.time()
            atomic_write(path, json.dumps(plan, indent=2, sort_keys=True).encode())
            return plan

    def _rollback(self, journal, journal_file):
        for move in reversed(journal["moved"]):
            source = Path(move["from"])
            destination = Path(move["to"])
            try:
                if destination.is_file() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, source)
                    # Remove an emptied category folder, but never a non-empty one.
                    parent = destination.parent
                    if parent.name in CATEGORIES or parent.name == FALLBACK:
                        try:
                            parent.rmdir()
                        except OSError:
                            pass
            except OSError:
                pass
        journal["state"] = "rolled_back"
        atomic_write(journal_file, json.dumps(journal).encode())

    def undo(self, identity, approved):
        """Reverse an applied run, refusing to clobber later changes."""
        if approved is not True:
            raise FileOrganizerError("Approve the undo explicitly.")
        journal_file = self._journal_dir(identity) / "journal.json"
        if journal_file.is_symlink() or not journal_file.is_file():
            raise FileOrganizerError("No run journal for that plan.")
        with self.lock:
            journal = json.loads(journal_file.read_text(encoding="utf-8"))
            if journal["state"] == "rolled_back":
                return journal
            if journal["state"] != "applied":
                raise FileOrganizerError("That run is not applied; nothing to undo.")
            for move in reversed(journal["moved"]):
                source = Path(move["from"])
                destination = Path(move["to"])
                if source.exists():
                    raise FileOrganizerError(
                        "Refusing to undo: a file reappeared at " + source.name)
                if not destination.is_file():
                    raise FileOrganizerError("Refusing to undo: missing " + destination.name)
            for move in reversed(journal["moved"]):
                source = Path(move["from"])
                destination = Path(move["to"])
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
                parent = destination.parent
                if parent.name in CATEGORIES or parent.name == FALLBACK:
                    try:
                        parent.rmdir()
                    except OSError:
                        pass
            journal["state"] = "undone"
            journal["undone_at"] = time.time()
            atomic_write(journal_file, json.dumps(journal).encode())
            return journal

    def history(self, limit=30):
        if self.root.is_symlink():
            return []
        if not self.root.is_dir():
            return []
        results = []
        for path in sorted(self.root.glob("*.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:max(0, min(int(limit), 100))]:
            if path.is_symlink():
                continue
            try:
                plan = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            results.append({key: plan.get(key) for key in
                            ("id", "directory", "state", "created", "applied")})
        return results

    def execute(self, action, payload):
        if action not in FILE_ORGANIZER_ACTIONS or not isinstance(payload, dict) \
                or set(payload) != FILE_ORGANIZER_ACTIONS[action]:
            raise FileOrganizerError("Invalid file organization request.")
        if action == "organize_scan":
            return self.scan(payload["directory"])
        if action == "organize_history":
            return self.history()
        if action == "organize_undo":
            return self.undo(payload["id"], payload["approved"])
        return self.apply(payload["id"], payload["plan_hash"], payload["approved"])
