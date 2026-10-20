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
    "files_intelligence_scan": ({"directory"}, {"large_mb", "old_days", "near_dup"}),
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


# Installer packages we can recognize by extension. Advisory only.
INSTALLER_EXTENSIONS = {".msi", ".msix", ".appx", ".msp", ".dmg", ".pkg",
                        ".deb", ".rpm", ".apk", ".appimage"}
INSTALLER_NAME_HINTS = ("setup", "installer", "install", "vcredist", "runtime")

# Download-duplicate name patterns, e.g. "report (1).pdf", "report - copy.pdf".
_DOWNLOAD_DUP = re.compile(r"(?i)(?:[ _-]+\(?\d+\)?|[ _-]+copy(?:\s*\(\d+\))?)$")

# Text-like extensions worth fuzzy comparing. Binary formats are excluded.
NEAR_DUP_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".py", ".js",
                       ".ts", ".tsx", ".jsx", ".html", ".css", ".xml", ".yaml",
                       ".yml", ".ini", ".cfg", ".sql", ".rst"}


def _is_installer(path):
    if path.suffix.lower() in INSTALLER_EXTENSIONS:
        return True
    name = path.name.lower()
    return path.suffix.lower() == ".exe" and any(hint in name for hint in INSTALLER_NAME_HINTS)


def _installer_family(path):
    """Normalize an installer name to a comparable family key (no version)."""
    stem = path.stem.lower()
    stem = re.sub(r"[_\-. ]?v?\d+(?:\.\d+)*", "", stem)
    stem = re.sub(r"[_\-.]?(x64|x86|amd64|win32|win64|setup|installer|install)", "", stem)
    return re.sub(r"[^a-z0-9]+", "", stem)


def _download_key(path):
    """Strip a download-duplicate suffix to reveal the original name."""
    stem = path.stem
    stripped = _DOWNLOAD_DUP.sub("", stem)
    return (path.parent, (stripped or stem).casefold() + path.suffix.casefold())


def _shingles(text, width=4):
    tokens = re.findall(r"\w+", text.lower())
    if len(tokens) < width:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + width]) for i in range(len(tokens) - width + 1)}


def _jaccard(left, right):
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


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

    # --- PC optimization detectors (read-only) ---------------------------
    def _near_duplicates(self, files, threshold=0.8, max_files=400):
        """Fuzzy text similarity. Only text-like, same-size-bucket files compared.

        Bucketing by size band keeps this far from O(n^2) on real folders; the
        file budget caps worst-case work. Binary formats are skipped.
        """
        candidates = [p for p in files if p.suffix.lower() in NEAR_DUP_EXTENSIONS]
        candidates = candidates[:max_files]
        texts, sizes = {}, {}
        for path in candidates:
            try:
                data = path.read_bytes()[:65536]
            except OSError:
                continue
            try:
                texts[path] = data.decode("utf-8-sig", errors="ignore")
            except Exception:
                continue
            sizes[path] = len(data)
        buckets = {}
        for path in texts:
            buckets.setdefault(round(sizes[path] ** 0.5), []).append(path)
        groups = []
        seen = set()
        for paths in buckets.values():
            signatures = {p: _shingles(texts[p]) for p in paths}
            for i, left in enumerate(paths):
                for right in paths[i + 1:]:
                    if (left, right) in seen:
                        continue
                    seen.add((left, right))
                    score = _jaccard(signatures[left], signatures[right])
                    if score >= threshold:
                        groups.append({
                            "similarity": round(score, 3),
                            "paths": [str(left), str(right)],
                        })
        groups.sort(key=lambda item: -item["similarity"])
        return groups[:100]

    def _redundant_installers(self, files):
        """Installer packages, grouped by family, flagging multiple versions."""
        installers = [p for p in files if _is_installer(p)]
        families = {}
        for path in installers:
            families.setdefault(_installer_family(path), []).append(path)
        redundant = []
        for family, paths in families.items():
            if len(paths) > 1 and family:
                redundant.append({
                    "family": family,
                    "count": len(paths),
                    "paths": [str(p) for p in sorted(paths, key=lambda p: str(p).casefold())],
                })
        redundant.sort(key=lambda item: -item["count"])
        return {
            "installers": [{"path": str(p), "size": self._size(p)} for p in installers],
            "redundant": redundant,
        }

    def _size(self, path):
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _duplicate_downloads(self, files):
        """Files whose names carry a download-duplicate suffix, grouped by origin."""
        groups = {}
        for path in files:
            if _DOWNLOAD_DUP.search(path.stem):
                groups.setdefault(_download_key(path), []).append(path)
        duplicates = []
        for (_, key), paths in groups.items():
            origin = key.rsplit("/", 1)[-1]
            duplicates.append({"original": origin, "count": len(paths),
                               "paths": [str(p) for p in sorted(paths, key=lambda p: str(p).casefold())]})
        duplicates.sort(key=lambda item: -item["count"])
        return duplicates

    def _recommendations(self, report):
        """Aggregate safe, read-only optimization recommendations. Changes nothing."""
        recs = []
        if report["duplicates"]:
            recs.append({"kind": "exact_duplicates", "count": len(report["duplicates"]),
                         "reclaimable_bytes": sum(d["size"] * (d["count"] - 1) for d in report["duplicates"]),
                         "advice": "Review exact duplicates; keep one copy each."})
        if report["near_duplicates"]:
            recs.append({"kind": "near_duplicates", "count": len(report["near_duplicates"]),
                         "advice": "Review similar documents; they may be revisions worth keeping."})
        if report["duplicate_downloads"]:
            recs.append({"kind": "duplicate_downloads", "count": len(report["duplicate_downloads"]),
                         "advice": "Download duplicates look safe to remove after review."})
        if report["redundant_installers"]:
            recs.append({"kind": "redundant_installers", "count": len(report["redundant_installers"]),
                         "advice": "Keep the newest installer only; older versions are redundant."})
        if report["temp_files"]:
            recs.append({"kind": "temporary_files", "count": len(report["temp_files"]),
                         "reclaimable_bytes": sum(t["size"] for t in report["temp_files"]),
                         "advice": "Temporary artifacts are usually safe to remove."})
        if report["large_files"]:
            recs.append({"kind": "large_files", "count": len(report["large_files"]),
                         "advice": "Confirm large files are still needed; archive if not."})
        return {"recommendations": recs,
                "recommendations_note": "Advisory only. No file is moved, archived or deleted by this scan."}

    # --- scan (read-only) ------------------------------------------------
    def scan(self, directory, large_mb=100, old_days=365, near_dup=None):
        folder = self._directory(directory)
        if type(large_mb) not in (int, float) or not 1 <= large_mb <= 100_000:
            raise FileIntelligenceError("large_mb must be between 1 and 100000.")
        if type(old_days) not in (int, float) or not 1 <= old_days <= 3650:
            raise FileIntelligenceError("old_days must be between 1 and 3650.")
        if near_dup is not None and not isinstance(near_dup, bool):
            raise FileIntelligenceError("near_dup must be true or false.")

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

        near_duplicates = self._near_duplicates(files) if near_dup else []
        redundancy = self._redundant_installers(files)
        duplicate_downloads = self._duplicate_downloads(files)

        report = {
            "directory": str(folder),
            "scanned_at": now,
            "file_count": len(files),
            "hashed_count": hashed,
            "truncated": truncated,
            "limits": {"max_entries": MAX_ENTRIES, "max_depth": MAX_DEPTH},
            "duplicates": duplicates,
            "near_duplicates": near_duplicates,
            "large_files": large[:200],
            "old_files": old[:200],
            "temp_files": temp[:200],
            "installers": redundancy["installers"][:200],
            "redundant_installers": redundancy["redundant"],
            "duplicate_downloads": duplicate_downloads,
            "reclaimable_bytes": sum(item["size"] * (item["count"] - 1) for item in duplicates)
                                + sum(item["size"] for item in temp),
            "note": ("Read-only report. Nothing was moved or deleted. Acting on these "
                     "findings requires a separate approved, journalled operation."),
        }
        report.update(self._recommendations(report))
        return report

    def execute(self, action, payload):
        if action not in INTELLIGENCE_ACTIONS or not isinstance(payload, dict):
            raise FileIntelligenceError("Invalid file intelligence request.")
        required, optional = INTELLIGENCE_ACTIONS[action]
        keys = set(payload)
        if not required <= keys or not keys <= (required | optional):
            raise FileIntelligenceError("Invalid file intelligence request.")
        return self.scan(payload["directory"], payload.get("large_mb", 100),
                         payload.get("old_days", 365), near_dup=payload.get("near_dup"))
