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
    "files_search": ({"directory", "query"}, set()),
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


# --- natural-language filesystem search (read-only) ---------------------
_QUERY_STOPWORDS = frozenset({
    "files", "file", "find", "all", "my", "in", "the", "show", "me", "list",
    "of", "with", "that", "are", "any", "less", "more", "than", "from",
    "over", "bigger", "larger", "smaller", "older", "newer", "modified",
    "and", "or", "no", "not", "is", "was", "please", "search", "sort",
})

_UNIT_DAYS = {"day": 1, "days": 1, "week": 7, "weeks": 7,
              "month": 30, "months": 30, "year": 365, "years": 365}
_SIZE_BYTES = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3,
               "byte": 1, "bytes": 1}

_EXTENSION_WORDS = {
    "pdf": ".pdf", "text": ".txt", "excel": ".xlsx", "xlsx": ".xlsx",
    "spreadsheet": ".xlsx", "word": ".docx", "docx": ".docx", "doc": ".doc",
    "csv": ".csv", "image": ".png", "png": ".png", "jpg": ".jpg",
    "jpeg": ".jpg", "photo": ".jpg", "python": ".py", "json": ".json",
    "markdown": ".md", "log": ".log", "zip": ".zip", "archive": ".zip",
    "exe": ".exe", "msi": ".msi", "powerpoint": ".pptx", "pptx": ".pptx",
}


def parse_query(text):
    """Heuristic NL query parser. Returns the machine-readable search intent.

    Understands: size thresholds ("larger than 50 mb"), age ("older than
    3 months", "newer than a week"), extensions (".pdf", "pdf files",
    "excel files"), and free keywords (stopwords dropped). Unknown text is
    treated as keywords. Nothing here executes anything.
    """
    if not isinstance(text, str) or not text.strip():
        raise FileIntelligenceError("Enter a natural-language search query.")
    lowered = text.lower()
    result = {"keywords": [], "extensions": [], "min_size_bytes": None,
              "max_age_days": None, "age_direction": None}

    size = re.search(r"(?:over|larger|bigger|greater)\s+than\s+(\d+(?:\.\d+)?)"
                     r"\s*(kib|mib|gib|gb|mb|kb|bytes|byte)?", lowered)
    if size:
        magnitude = float(size.group(1))
        unit = (size.group(2) or "mb").lower()
        if unit == "mib":
            unit = "mb"
        elif unit == "gib":
            unit = "gb"
        elif unit == "kib":
            unit = "kb"
        result["min_size_bytes"] = magnitude * _SIZE_BYTES[unit]
    else:
        plain = re.search(r"(\d+(?:\.\d+)?)\s*(gb|mb|kb)\b", lowered)
        if plain:
            result["min_size_bytes"] = float(plain.group(1)) * _SIZE_BYTES[plain.group(2)]

    age = re.search(r"older than\s+(?:a\s+)?(?:(\d+|one|two|three|four|five)\s+)?"
                    r"(day|days|week|weeks|month|months|year|years)", lowered)
    newer = re.search(r"newer than\s+(?:a\s+)?(?:(\d+|one|two|three|four|five)\s+)?"
                      r"(day|days|week|weeks|month|months|year|years)", lowered)
    last = re.search(r"last\s+(?:(\d+|one|two|three|four|five)\s*)?"
                     r"(day|days|week|weeks|month|months|year|years)", lowered)
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

    def _value(raw):
        return words.get(raw) or int(raw)

    if age:
        result["max_age_days"] = (_value(age.group(1)) if age.group(1) else 1) * _UNIT_DAYS[age.group(2)]
        result["age_direction"] = "older"
    elif newer:
        result["max_age_days"] = (_value(newer.group(1)) if newer.group(1) else 1) \
            * _UNIT_DAYS[newer.group(2)]
        result["age_direction"] = "newer"
    elif last:
        result["max_age_days"] = (_value(last.group(1)) if last.group(1) else 1) \
            * _UNIT_DAYS[last.group(2)]
        result["age_direction"] = "newer"

    for dot, ext in re.findall(r"(\.)?([a-z0-9]{2,5})\b", lowered):
        token = ext
        if not dot and token not in _EXTENSION_WORDS:
            continue
        mapped = (token if dot else _EXTENSION_WORDS[token])
        candidate = "." + mapped if not mapped.startswith(".") else mapped
        if candidate in NEAR_DUP_EXTENSIONS or candidate in {".pdf", ".docx", ".xlsx",
                                                             ".csv", ".png", ".jpg", ".zip", ".exe"}:
            if candidate not in result["extensions"]:
                result["extensions"].append(candidate)

    consumed = " ".join(piece.group(0) for piece in (size, age, newer, last) if piece)
    consumed += " " + " ".join(ext.lstrip(".") for ext in result["extensions"])
    remaining = re.sub(r"[.\d]+", " ", lowered)
    for token in re.findall(r"[a-z0-9]+", remaining):
        if token in _QUERY_STOPWORDS or token in _EXTENSION_WORDS \
                or token in _UNIT_DAYS or token in words:
            continue
        if token and (consumed and token not in consumed and len(token) >= 2):
            result["keywords"].append(token)
    result["keywords"] = list(dict.fromkeys(result["keywords"]))[:12]
    if not result["keywords"] and not result["extensions"] \
            and result["min_size_bytes"] is None and result["max_age_days"] is None:
        raise FileIntelligenceError("Query had no recognisable filters or keywords.")
    return result


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
        if path == Path(path.anchor) or path == Path.home():
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

    # --- natural-language search (read-only) -----------------------------
    def search(self, directory, query):
        folder = self._directory(directory)
        intent = parse_query(query)
        files, truncated = self._walk(folder)
        now = time.time()
        results = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            if intent["extensions"] and path.suffix.lower() not in intent["extensions"]:
                continue
            if intent["min_size_bytes"] is not None and stat.st_size < intent["min_size_bytes"]:
                continue
            if intent["max_age_days"] is not None:
                age_days = (now - stat.st_mtime) / 86400
                if intent["age_direction"] == "older" and age_days < intent["max_age_days"]:
                    continue
                if intent["age_direction"] == "newer" and age_days > intent["max_age_days"]:
                    continue
            casefold_name = path.name.casefold()
            casefold_dir = str(path.parent).casefold()
            score = 0
            for keyword in intent["keywords"]:
                if keyword in casefold_name:
                    score += 3
                elif keyword in casefold_dir:
                    score += 1
            if intent["keywords"] and score == 0:
                continue
            results.append({
                "path": str(path), "size": stat.st_size, "modified": stat.st_mtime,
                "score": score,
            })
        results.sort(key=lambda item: (-item["score"], -item["size"], item["path"]))
        return {
            "directory": str(folder), "query": query, "intent": intent,
            "file_count": len(files), "truncated": truncated,
            "results": results[:100],
            "note": ("Read-only search over names, paths, sizes and dates. Keywords "
                     "match by substring; refine the query if results are noisy. "
                     "Nothing is opened, indexed or modified."),
        }

    def execute(self, action, payload):
        if action not in INTELLIGENCE_ACTIONS or not isinstance(payload, dict):
            raise FileIntelligenceError("Invalid file intelligence request.")
        required, optional = INTELLIGENCE_ACTIONS[action]
        keys = set(payload)
        if not required <= keys or not keys <= (required | optional):
            raise FileIntelligenceError("Invalid file intelligence request.")
        if action == "files_search":
            return self.search(payload["directory"], payload["query"])
        return self.scan(payload["directory"], payload.get("large_mb", 100),
                         payload.get("old_days", 365), near_dup=payload.get("near_dup"))
