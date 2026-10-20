"""Isolated GitHub import: clone, license reading and a dependency map.

Clones a public GitHub repository into a throwaway directory so its architecture,
licenses and dependencies can be inspected, then removes it. It never executes
repository code: no hooks, no install scripts, no submodules, no Git LFS, no
build step. Only `https://github.com/<owner>/<repo>` is accepted.

Source *sampling* is delegated to `spark_repo_upgrade.snapshot`, so the same
bounded, symlink-safe evidence rules apply to a cloned repo as to a local one.
This module adds what the local path lacks: the clone itself, license reading and
a dependency map.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from spark_maintenance import MaintenanceError, digest
from spark_repo_upgrade import eligible, linked, snapshot


class RepoImportError(ValueError):
    pass


GITHUB_URL = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?/?$")

LICENSE_FILENAMES = ("license", "license.md", "license.txt", "license.rst",
                     "copying", "copying.md", "copying.txt", "unlicense",
                     "license-mit", "license-apache")

# Ordered: first match wins. Value is (spdx, class).
_LICENSE_HINTS = (
    ("mit license", ("MIT", "permissive")),
    ("apache license", ("Apache-2.0", "permissive")),
    ("bsd 3-clause", ("BSD-3-Clause", "permissive")),
    ("bsd 2-clause", ("BSD-2-Clause", "permissive")),
    ("isc license", ("ISC", "permissive")),
    ("mozilla public license", ("MPL-2.0", "weak-copyleft")),
    ("gnu lesser general public license", ("LGPL", "weak-copyleft")),
    ("gnu affero general public license", ("AGPL", "strong-copyleft")),
    ("gnu general public license", ("GPL", "strong-copyleft")),
    ("the unlicense", ("Unlicense", "permissive")),
)

PERMISSIVE = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "Unlicense"}


def parse_github_url(url):
    """Return (owner, repo) for an allowed GitHub URL, else raise."""
    if not isinstance(url, str) or len(url) > 300:
        raise RepoImportError("Provide a GitHub repository URL.")
    match = GITHUB_URL.match(url.strip())
    if not match:
        raise RepoImportError("Only public https://github.com/<owner>/<repo> URLs are accepted.")
    owner, repo = match.group(1), match.group(2)
    if repo in {".", ".."}:
        raise RepoImportError("Invalid repository name.")
    return owner, repo


def _clone(url, destination, *, timeout):
    """Shallow, code-execution-free clone. Hooks and submodules disabled."""
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                              "COMSPEC", "PATHEXT", "LOCALAPPDATA", "APPDATA",
                              "USERPROFILE", "HOME"}}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    command = [ "git", "-c", "core.hooksPath=" + os.devnull,
               "-c", "core.symlinks=false",
               "clone", "--depth", "1", "--single-branch", "--no-tags",
               "--recurse-submodules=no", url, str(destination)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout,
                                text=True, encoding="utf-8", errors="replace", env=env)
    except FileNotFoundError:
        raise RepoImportError("Git is not installed or not on PATH.") from None
    except subprocess.TimeoutExpired:
        raise RepoImportError("Clone timed out; try a smaller repository.") from None
    if result.returncode:
        raise RepoImportError("Clone failed. Confirm the repository is public and the URL is correct.")


def _read_license(root):
    """Read the first license-like file found. Returns (spdx, class, filename, text)."""
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [f for f in folders if not f.startswith(".") and f not in {"node_modules", ".git"}]
        for name in sorted(files):
            if name.lower() in LICENSE_FILENAMES:
                path = Path(directory) / name
                if linked(path):
                    continue
                try:
                    text = path.read_bytes()[:16384].decode("utf-8-sig", errors="replace")
                except OSError:
                    continue
                low = text.lower()
                for hint, verdict in _LICENSE_HINTS:
                    if hint in low:
                        return (*verdict, path.name, text)
                return ("UNKNOWN", "unknown", path.name, text)
    return (None, "none", None, "")


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def dependency_map(root):
    """Best-effort dependency inventory across common manifests. Read-only."""
    deps, dev_deps = {}, {}

    def add(store, name, version, source):
        if isinstance(name, str) and name and name not in store:
            store[name] = {"requirement": str(version)[:60], "source": source}

    package = _read_json(Path(root) / "package.json")
    if isinstance(package, dict):
        for name, version in (package.get("dependencies") or {}).items():
            add(deps, name, version, "package.json")
        for name, version in (package.get("devDependencies") or {}).items():
            add(dev_deps, name, version, "package.json")

    requirements = Path(root) / "requirements.txt"
    if requirements.is_file() and not linked(requirements):
        try:
            for line in requirements.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    name = re.split(r"[<>=!~\[; ]", line, 1)[0]
                    add(deps, name, line[len(name):].strip() or "*", "requirements.txt")
        except OSError:
            pass

    pyproject = Path(root) / "pyproject.toml"
    if pyproject.is_file() and not linked(pyproject):
        try:
            text = pyproject.read_text(encoding="utf-8-sig")
        except OSError:
            text = ""
        # Minimal, dependency-free TOML scan: only single-line string arrays.
        for name, version in re.findall(r'["\']([A-Za-z0-9_.\-]+)\s*([<>=!~]{1,2}[^"\']*)["\']', text):
            add(deps, name, version, "pyproject.toml")

    return {"python": sorted(deps), "node": sorted(dev_deps),
            "dependencies": deps, "dev_dependencies": dev_deps,
            "count": len(deps) + len(dev_deps)}


def import_evidence(url, *, selected=None, timeout=120, max_bytes=200 * 1024 * 1024):
    """Clone `url`, gather license + dependency evidence, then delete the clone.

    Returns the same source-sample shape as `snapshot` plus `imported` metadata.
    No repository code is executed at any point.
    """
    owner, repo = parse_github_url(url)
    if not isinstance(timeout, int) or not 30 <= timeout <= 600:
        raise RepoImportError("Clone timeout must be 30-600 seconds.")
    if selected is not None and (not isinstance(selected, list) or len(selected) > 16
                                 or any(not isinstance(item, str) for item in selected)):
        raise RepoImportError("Select at most 16 reference paths.")

    workdir = Path(tempfile.mkdtemp(prefix="spark-import-"))
    target = workdir / "repo"
    try:
        _clone(url, target, timeout=timeout)
        if _tree_bytes(target, limit=max_bytes) > max_bytes:
            raise RepoImportError("Repository checkout exceeds the size limit.")
        spdx, license_class, license_file, _ = _read_license(target)
        # Reuse the bounded, symlink-safe sampler used for local repositories.
        evidence = snapshot(str(target), selected or [])
        evidence["repository"] = "%s/%s" % (owner, repo)
        evidence["imported"] = {
            "owner": owner, "repo": repo, "url": url,
            "clone_shallow": True, "submodules": False, "hooks_disabled": True,
            "code_executed": False,
        }
        evidence["license"] = {
            "spdx": spdx, "class": license_class, "file": license_file,
            "permissive": spdx in PERMISSIVE,
            "note": ("No license file found; treat as all-rights-reserved and do not copy code."
                     if license_class == "none" else
                     "License text is heuristic; confirm before reusing any code."),
        }
        evidence["dependency_map"] = dependency_map(target)
        evidence["limitations"] = list(evidence.get("limitations", [])) + [
            "Imported repository code is never executed, installed or built.",
            "Only a shallow, single-branch clone without submodules is inspected.",
            "License classification is textual and may be wrong; verify manually.",
        ]
        return evidence
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _tree_bytes(root, *, limit):
    total = 0
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [f for f in folders if f != ".git"]
        for name in files:
            path = Path(directory) / name
            if name == ".git" or path.is_symlink():
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
            if total > limit:
                return total
    return total
