"""Read-only File Intelligence: duplicates, large/old files, temp inventory.

Master-prompt Section 5 "File Intelligence", deliberately read-only. This module
inspects an approved directory tree and reports findings; it never moves, copies
or deletes anything. Acting on a finding is left to the audited, journalled
movers (`spark_file_organizer`, `spark_pc_access`), each of which has its own
approval gate.

Safety and bounds:

* Confined to an allowed root, refuses whole drives / the home folder as a
  scan target, and never follows symlinks or recurses past a fixed depth/file
  budget.
* Duplicate detection hashes only files that share a byte size with another
  file, so a directory of unique files is almost never hashed.
* No path, size or hash is written to disk; results are returned, not stored.
"""
import hashlib
import os
import re
import time
from pathlib import Path


class FileIntelligenceError(ValueError):
    pass


INTELLIGENCE_ACTIONS = {
    "files_intelligence_scan": ({"directory"}, {"large_mb", "old_days"}),
}

MAX_ENTRIES = 20000
MAX_DEPTH = 8
HASH_CHUNK = 1024 * 1024

# Extensions that are almost always safe-to-review temporary artifacts. This is
# an advisory classification only; nothing is deleted.
TEMP_EXTENSIONS = {".tmp", ".temp", ".crdownload", ".part", ".partial", ".bak",
                   ".old", ".log1", ".dmp", ".~"}
TEMP_NAMES = {"thumbs.db", "desktop.ini"}


def _is_temp(path):
    name = path.name.lower()
    if name in TEMP_NAMES:
        return True
    if path.suffix.lower() in TEMP_EXTENSIONS:
        return True
    return bool(re.match(r"^~\$", name))  # Office lock files


class FileIntelligence:
    def __init__(self, root=None):
        self._allowed_root = Path(root).resolve() if root else None

    # --- guards ----------------------------------------------------------
    def _directory(self, value):
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise FileIntelligenceError("Supply a directory path.")
        path = Path(os.path.expandvars(value)).expanduser()
        if not path.is_absolute():
            raise FileIntelligenceError("Use an absolute directory path.")
        path = path.resolve()
        if self._allowed_root is not None and not path.is_relative_to(self._allowed_root):
            raise FileIntelligenceError("That directory is outside the allowed root.")
        if path.is_symlink() or not path.is_dir():
            raise FileIntelligenceError("That is not an existing, non-linked directory.")
        if path == path.anchor or path == Path.home():
            raise FileIntelligenceError("Refusing to scan a whole drive or the home folder.")
        return path

    def _walk(self, folder):
        """Bounded, symlink-safe walk. Returns (files, truncated)."""
        files = []
        truncated = False
        stack = [(folder, 0)]
        while stack:
            current, depth = stack.pop()
            if depth > MAX_DEPTH:
                truncated = True
                continue
            try:
                entries = sorted(current.iterdir(), key=lambda p: p.name.casefold())
            except OSError:
                continue
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    stack.append((entry, depth + 1))
                elif entry.is_file():
                    if len(files) >= MAX_ENTRIES:
                        truncated = True
                        break
                    files.append(entry)
        return files, truncated

    def _hash(self, path):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(HASH_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    # --- scan (read-only) ------------------------------------------------
    def scan(self, directory, large_mb=100, old_days=365):
        folder = self._directory(directory)
        if type(large_mb) not in (int, float) or not 1 <= large_mb <= 100_000:
            raise FileIntelligenceError("large_mb must be between 1 and 100000.")
        if type(old_days) not in (int, float) or not 1 <= old_days <= 3650:
            raise FileIntelligenceError("old_days must be between 1 and 3650.")

        files, truncated = self._walk(folder)
        now = time.time()
        large_threshold = int(large_mb * 1024 * 1024)
        old_threshold = now - old_days * 86400

        # Group by size first; only same-size files are ever hashed.
        by_size = {}
        for path in files:
            try:
                by_size.setdefault(path.stat().st_size, []).append(path)
            except OSError:
                continue

        duplicates = []
        hashed = 0
        for size, group in by_size.items():
            if len(group) < 2:
                continue
            by_hash = {}
            for path in group:
                try:
                    digest = self._hash(path)
                except OSError:
                    continue
                hashed += 1
                by_hash.setdefault(digest, []).append(path)
            for digest, same in by_hash.items():
                if len(same) > 1:
                    duplicates.append({
                        "sha256": digest,
                        "size": size,
                        "count": len(same),
                        "paths": [str(p) for p in sorted(same, key=lambda p: str(p).casefold())],
                    })
        duplicates.sort(key=lambda item: (-item["size"] * item["count"], item["sha256"]))

        large = []
        old = []
        temp = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            record = {"path": str(path), "size": stat.st_size,
                      "modified": stat.st_mtime}
            if stat.st_size >= large_threshold:
                large.append(record)
            if stat.st_mtime <= old_threshold:
                old.append(record)
            if _is_temp(path):
                temp.append(record)
        large.sort(key=lambda item: -item["size"])
        old.sort(key=lambda item: item["modified"])
        temp.sort(key=lambda item: -item["size"])

        return {
            "directory": str(folder),
            "scanned_at": now,
            "file_count": len(files),
            "hashed_count": hashed,
            "truncated": truncated,
            "limits": {"max_entries": MAX_ENTRIES, "max_depth": MAX_DEPTH},
            "duplicates": duplicates,
            "large_files": large[:200],
            "old_files": old[:200],
            "temp_files": temp[:200],
            "reclaimable_bytes": sum(item["size"] * (item["count"] - 1) for item in duplicates)
                                + sum(item["size"] for item in temp),
            "note": ("Read-only report. Nothing was moved or deleted. Acting on these "
                     "findings requires a separate approved, journalled operation."),
        }

    def execute(self, action, payload):
        if action not in INTELLIGENCE_ACTIONS or not isinstance(payload, dict):
            raise FileIntelligenceError("Invalid file intelligence request.")
        required, optional = INTELLIGENCE_ACTIONS[action]
        keys = set(payload)
        if not required <= keys or not keys <= (required | optional):
            raise FileIntelligenceError("Invalid file intelligence request.")
        return self.scan(payload["directory"], payload.get("large_mb", 100),
                         payload.get("old_days", 365))
