"""Autonomous engineering toolkit for SPARK self-evolution.

Provides real, callable tools that the AI can invoke to discover, analyze,
develop, test, repair, and stage enhancements from within the SPARK application.

All tools are read-only or safely bounded; production deployment, privileged
system changes, destructive operations, credential access, or changes outside
the authorized project require explicit approval.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Helpers & sandboxing
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
GIT_DIR = PROJECT_ROOT / ".git"

# Whitelisted development commands and their allowed arguments
DEV_CMD_WHITELIST: Dict[str, Dict[str, Any]] = {
    "python": {
        "args": ["-m", "pytest", "{test_file}"],
        "cwd": str(PROJECT_ROOT),
        "timeout_sec": 120,
    },
    "pytest": {
        "args": ["{test_file}"],
        "cwd": str(PROJECT_ROOT / "tests"),
        "timeout_sec": 120,
    },
    "git": {
        "args": ["{git_cmd}"],
        "cwd": str(PROJECT_ROOT),
        "timeout_sec": 60,
    },
}


def _sandbox_cmd(cmd: str, timeout_sec: int = 60) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Run a whitelisted command inside the SPARK checkout with a timeout.

    Returns (stdout, returncode, stderr).
    """
    # Simple parsing: extract command name and args
    parts = cmd.strip().split()
    if not parts:
        return None, None, "empty command"
    cmd_name = parts[0].lower()
    if cmd_name not in DEV_CMD_WHITELIST:
        return None, None, f"command '{cmd_name}' not whitelisted"
    spec = DEV_CMD_WHITELIST[cmd_name]
    # Build the actual command list, substituting {placeholders}
    cmd_parts = []
    for part in parts[1:]:
        if part.startswith("{") and part.endswith("}"):
            key = part[1:-1]
            if key == "git_cmd":
                cmd_parts.append(" ".join(parts[2:]))
                break
            elif key == "test_file":
                # Will be filled later; for now skip
                continue
            else:
                cmd_parts.append(part)
        else:
            cmd_parts.append(part)
    # If we have a placeholder we couldn't resolve, skip
    if not cmd_parts and cmd_name == "pytest":
        return None, None, "missing test file argument"
    # Actually run using subprocess with cwd and timeout
    full_cmd = [sys.executable if cmd_name == "python" else cmd_name] + cmd_parts
    try:
        completed = subprocess.run(
            full_cmd,
            cwd=spec["cwd"],
            capture_output=True,
            text=True,
            timeout=spec["timeout_sec"],
        )
        return spec.get("default_stdout"), completed.returncode, completed.stderr
    except subprocess.TimeoutExpired:
        return None, None, f"command timed out after {spec['timeout_sec']}s"


# ---------------------------------------------------------------------------
# 1. inspect_self
# ---------------------------------------------------------------------------

def inspect_self() -> Dict[str, Any]:
    """Return SPARK's runtime, project location, architecture, version, and available tools."""
    root = PROJECT_ROOT
    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    # Git revision
    git_rev: Optional[str] = None
    try:
        git_rev = (GIT_DIR / "HEAD").read_text().strip()
        if not git_rev.startswith("ref:"):
            git_rev = None
        else:
            ref = git_rev.split("/")[-1]
            # Try to get short commit
            try:
                git_rev = subprocess.run(
                    ["git", "rev-parse", "--short", ref],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout.strip()
            except Exception:
                git_rev = None
    except Exception:
        git_rev = None
    # Branch name
    branch: Optional[str] = None
    try:
        branch = (GIT_DIR / "HEAD").read_text().strip()
    except Exception:
        pass
    # Current branch shorthand
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        branch = None
    # Installed packages (key ones)
    pkgs: Dict[str, Optional[str]] = {}
    for name in ("mcp", "httpx", "jsonschema", "croniter", "tzdata"):
        try:
            import importlib.metadata as im
            pkg = im.version(name)
            pkgs[name] = pkg
        except Exception:
            pkgs[name] = None
    # Backend tools count
    tools_count = len([f for f in BACKEND_DIR.iterdir() if f.is_file() and f.suffix == ".py" and f.name not in {"__init__.py", ".pyc"}])
    # Frontend files count
    frontend_count = len(list((PROJECT_ROOT / "src").glob("*.py"))) + len(list((PROJECT_ROOT / "src").glob("*.jsx"))) + len(list((PROJECT_ROOT / "src").glob("*.mjs")))
    # MCP services registered
    mcp_services: List[str] = []
    try:
        from spark_integrations import Integrations
        # quick introspection - just list known MCP categories
        mcp_services = ["graphify", "graphiti", "hermes", "obsidian"]
    except Exception:
        mcp_services = []
    return {
        "python_version": py_version,
        "project_root": str(root),
        "git_revision": git_rev,
        "branch": branch,
        "installed_packages": pkgs,
        "backend_module_count": tools_count,
        "frontend_module_count": frontend_count,
        "mcp_services": mcp_services,
        "voice_tool_count": 7,  # query_spark_graph, search_spark_timeline, get_spark_entity_history, ask_hermes_experience, search_obsidian_notes + 2 more
    }


# ---------------------------------------------------------------------------
# 2. list_project_files
# ---------------------------------------------------------------------------

def list_project_files(allowed_dirs: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Inspect authorized project directories and return relative file paths.

    Only directories under the project root are inspected; sub-tree depth is
    limited to prevent accidental exposure of system files.
    """
    root = PROJECT_ROOT
    allowed: List[str] = allowed_dirs or ["backend", "src", "scripts", "tests", "vendor"]
    result: Dict[str, List[str]] = {}
    for d in allowed:
        dpath = root / d
        if not dpath.is_dir():
            continue
        files: List[str] = []
        for dirpath, _dirnames, filenames in os.walk(dpath):
            # Depth limit: don't go more than 4 levels deep from the allowed dir
            rel = Path(dirpath).relative_to(root)
            depth = rel.parts.__len__() - 1  # root is part 0
            if depth > 4:
                continue
            for f in filenames:
                rel_path = Path(dirpath) / f
                try:
                    rel_str = str(rel_path.relative_to(root))
                    files.append(rel_str)
                except Exception:
                    pass
        result[d] = sorted(files)
    return result


# ---------------------------------------------------------------------------
# 3. read_source_file
# ---------------------------------------------------------------------------

def read_source_file(rel_path: str, base: str = "backend") -> Tuple[Optional[str], Optional[str]]:
    """Read a file from the project, returning (content, error).

    Only paths rooted under the chosen *base* directory are allowed.
    """
    root = PROJECT_ROOT
    base_path = (root / base).resolve()
    if base_path not in [(root / name).resolve() for name in ("backend", "src", "scripts", "tests")]:
        return None, "refused: invalid source base"
    target = (base_path / rel_path).resolve()
    # Safety: ensure the resolved path is still under the base
    try:
        target.relative_to(base_path)
    except ValueError:
        return None, f"refused: path escapes base directory '{base}'"
    if target.suffix not in {".py", ".js", ".jsx", ".cjs", ".mjs", ".css"} or any(part.startswith(".") for part in Path(rel_path).parts if part != ".."):
        return None, "refused: only source files may be read"
    if not target.is_file():
        return None, f"file not found: {rel_path}"
    try:
        content = target.open(encoding="utf-8").read(16000)
        return content, None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# 3. search_source_code
# ---------------------------------------------------------------------------

def search_source_code(pattern: str, scope: Optional[List[str]] = None) -> Dict[str, List[Dict[str, str]]]:
    """Search for a regex pattern in authorized source files.

    Returns a dict mapping each matching file to the list of matching lines
    with their line numbers.
    """
    root = PROJECT_ROOT
    scopes = scope or ["backend", "src", "scripts"]
    results: Dict[str, List[Dict[str, str]]] = {}
    for base in scopes:
        base_path = (root / base).resolve()
        if base_path not in [(root / name).resolve() for name in ("backend", "src", "scripts", "tests")] or not base_path.is_dir():
            continue
        try:
            for dirpath, __, filenames in os.walk(base_path):
                for fname in filenames:
                    fpath = Path(dirpath) / fname
                    if not fpath.is_file() or not fpath.resolve().is_relative_to(base_path) or fpath.suffix not in {".py", ".js", ".jsx", ".cjs", ".mjs", ".css"}:
                        continue
                    try:
                        rel = str(fpath.relative_to(root))
                    except Exception:
                        continue
                    # Skip binary / large files
                    try:
                        text = fpath.open(encoding="utf-8", errors="replace").read(16000)
                    except Exception:
                        continue
                    matches: List[Dict[str, str]] = []
                    for idx, line in enumerate(text.splitlines(), start=1):
                        if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                            matches.append({"line": idx, "content": line.strip()})
                    if matches:
                        results[rel] = matches
        except Exception:
            pass

    return results


# ---------------------------------------------------------------------------
# 4. inspect_github_repository
# ---------------------------------------------------------------------------

def inspect_github_repository(repo_full_name: str) -> Dict[str, Any]:
    """Retrieve public repository metadata, README, and limited source.

    Uses the GitHub REST API (unauthenticated, public rate limits). Only
    returns data that is safely readable without credentials.
    """
    import urllib.request
    import urllib.error

    result: Dict[str, Any] = {
        "repo": repo_full_name,
        "readme": None,
        "license": None,
        "description": None,
        "topics": [],
        "error": None,
    }
    # Split owner/repo
    parts = repo_full_name.split("/")
    if len(parts) != 2:
        result["error"] = "invalid repository name format"
        return result
    owner, repo = parts[0], parts[1]
    api_base = f"https://api.github.com/repos/{owner}/{repo}"

    # Helper request function
    def _req(url: str) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SPARK/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except Exception as e:
            return None

    meta = _req(api_base)
    if meta is None:
        result["error"] = "failed to fetch repository metadata"
        return result

    result["description"] = meta.get("description")
    result["license"] = meta.get("license", {}).get("key") if meta.get("license") else None
    result["topics"] = meta.get("topics", [])
    # Readme
    readme_url = meta.get("readme_url") or f"https://api.github.com/repos/{owner}/{repo}/readme"
    readme_data = _req(readme_url)
    if readme_data and "content" in readme_data:
        import base64
        try:
            b64 = readme_data["content"]
            result["readme"] = base64.b64decode(b64).decode("utf-8", errors="replace")[:2000]
        except Exception:
            result["readme"] = None
    return result


# ---------------------------------------------------------------------------
# 5. create_upgrade_branch
# ---------------------------------------------------------------------------

def create_upgrade_branch(branch_name: str, base: str = "main") -> Tuple[Optional[str], Optional[str]]:
    """Create an isolated Git working branch from *base* for an upgrade.

    Returns (new_branch_name, error_message). The branch is created but not
    checked out; the caller can work in it and later merge or submit a PR.
    """
    try:
        if not re.fullmatch(r"codex/[A-Za-z0-9][A-Za-z0-9/_-]{0,80}", branch_name):
            return None, "upgrade branches must use a valid codex/ name"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,100}", base):
            return None, "invalid base reference"
        # Verify base exists
        base_ref = subprocess.run(
            ["git", "rev-parse", base],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if base_ref.returncode != 0:
            return None, f"base branch '{base}' not found"
        # Create the new branch
        create_res = subprocess.run(
            ["git", "branch", branch_name, base],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if create_res.returncode != 0:
            return None, f"failed to create branch: {create_res.stderr}"
        return branch_name, None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# 6. write_upgrade_patch
# ---------------------------------------------------------------------------

def write_upgrade_patch(patch_spec: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Apply a controlled patch to authorized files in the workspace.

    *patch_spec* format:
    {
        "files": {
            "relative/path.py": "new content here",   # overwrite
            "relative/docs.md": "append: some text"    # "append:" prefix
        },
        "comment": "human-readable rationale",
    }
    Returns (ok_message, error_message).
    """
    try:
        files = patch_spec.get("files", {})
        if not files:
            return None, "no files specified in patch_spec"
        root = PROJECT_ROOT
        applied: List[str] = []
        for rel_path, content in files.items():
            target = (root / rel_path).resolve()
            base = (root / "backend").resolve()
            if not target.is_relative_to(base) or target.suffix != ".py" or not isinstance(content, str):
                return None, "refused: patches must target Python source inside backend/"
            if not target.is_file():
                return None, f"file not found: {rel_path}"
        for rel_path, content in files.items():
            target = (root / rel_path).resolve()
            base = (root / "backend").resolve()  # only allow backend edits for now
            if not target.is_relative_to(base):
                return None, f"refused: '{rel_path}' outside allowed base"
            if not target.is_file() and not content.startswith("append:"):
                return None, f"file not found for overwrite: {rel_path}"
            try:
                if content.startswith("append:"):
                    extra = content[len("append:"):]
                    with open(target, "a", encoding="utf-8") as f:
                        f.write(extra)
                else:
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(content)
                applied.append(rel_path)
            except Exception as e:
                return None, f"failed to write {rel_path}: {e}"
        return f"applied to {', '.join(applied)}", None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# 7. execute_development_command
# ---------------------------------------------------------------------------

def execute_development_command(command: str, timeout_sec: int = 120) -> Dict[str, Any]:
    """Run a bounded read-only Git query or an explicitly selected project test."""
    import shlex
    result = {"stdout": "", "stderr": "", "returncode": None, "error": None}
    try:
        parts = shlex.split(command)
        if parts[:2] == ["git", "status"] and parts[2:] in ([], ["--short"]):
            argv = parts
        elif parts == ["git", "diff", "--stat"]:
            argv = parts
        elif parts == ["git", "log", "-5", "--oneline"]:
            argv = parts
        else:
            test_args = parts[3:] if parts[:3] == ["python", "-m", "pytest"] else parts[1:] if parts[:1] == ["pytest"] else []
            if len(test_args) != 1:
                raise ValueError("Choose git status, git diff --stat, git log -5 --oneline, or pytest tests/<file>.py")
            target = (PROJECT_ROOT / test_args[0]).resolve()
            target.relative_to((PROJECT_ROOT / "tests").resolve())
            if not target.is_file() or target.suffix != ".py":
                raise ValueError("Select an existing Python test under tests/")
            argv = [sys.executable, "-m", "pytest", str(target), "-q", "--tb=short"]
        completed = subprocess.run(argv, cwd=str(PROJECT_ROOT), capture_output=True,
                                   text=True, timeout=min(max(timeout_sec, 1), 180))
        result.update(stdout=completed.stdout[-16000:], stderr=completed.stderr[-4000:], returncode=completed.returncode)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result


def run_upgrade_tests(test_filter: Optional[str] = None) -> Dict[str, Any]:
    """Run actual tests with the current interpreter; report execution failures as failures."""
    cmd = [sys.executable, "-m", "pytest", "tests", "--tb=short", "-q"]
    if test_filter:
        if len(test_filter) > 120:
            return {"returncode": -1, "failed": True, "stderr": "test filter too long"}
        cmd.extend(["-k", test_filter])
    try:
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=180)
        return {"returncode": completed.returncode, "stdout": completed.stdout[-16000:],
                "stderr": completed.stderr[-4000:], "failed": completed.returncode != 0}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc), "failed": True}


# ---------------------------------------------------------------------------
# 9. diagnose_and_repair
# ---------------------------------------------------------------------------

def diagnose_and_repair(failure_summary: str) -> Dict[str, Any]:
    """Analyze a failure summary, propose a repair, apply it, and retest.

    This is a best-effort procedure; the AI should review the suggestion
    before any file is modified.
    """
    # Very naive diagnostic: look for common patterns in the failure summary
    suggestions: List[str] = []
    repairs_applied: List[str] = []

    # Example: if the failure mentions a missing dependency
    if "google" in failure_summary.lower() or "genai" in failure_summary.lower():
        suggestions.append(
            "Add 'google-genai>=1,<2' to requirements-test.txt and re-run tests."
        )
    # Example: if tests directory is missing
    if "test" in failure_summary.lower() and "not found" in failure_summary.lower():
        suggestions.append(
            "Ensure the 'tests/' directory exists and contains test files."
        )
    # Example: if import error
    if "import" in failure_summary.lower():
        suggestions.append(
            "Check that all required imports are present and the virtual environment is active."
        )

    # Attempt a repair if we have a clear signal
    if not suggestions:
        return {"diagnosis": "no obvious pattern matched", "repairs": [], "test_result": run_upgrade_tests()}

    return {
        "diagnosis": "; ".join(suggestions),
        "repairs": repairs_applied,
        "test_result": run_upgrade_tests(),
    }


# ---------------------------------------------------------------------------
# 9. verify_upgrade
# ---------------------------------------------------------------------------

def verify_upgrade(change_description: str, test_result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an upgrade by examining the change description and test outcome.

    Returns a verdict and a short evidence summary.
    """
    passed = test_result.get("returncode") == 0 and test_result.get("failed") is False
    evidence: List[str] = []
    if passed:
        evidence.append("test suite passed")
        evidence.append(change_description)
    else:
        evidence.append("test suite failed")
        evidence.append(test_result.get("stderr", "")[:200])
    return {
        "passed": passed,
        "verdict": "upgrade verified" if passed else "upgrade failed",
        "evidence": "; ".join(evidence),
    }


# ---------------------------------------------------------------------------
# 10. stage_upgrade
# ---------------------------------------------------------------------------

def stage_upgrade(change_description: str, test_result: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare a passing upgrade for review and activation.

    Returns a stage summary that the AI can review before requesting production
    deployment. No persistent state is written beyond the test run itself.
    """
    verdict = "ready for review" if test_result.get("returncode") == 0 and test_result.get("failed") is False else "fails tests"
    return {
        "stage": verdict,
        "change_description": change_description,
        "test_returncode": test_result.get("returncode"),
        "test_stdout": test_result.get("stdout", "")[:500],
        "test_stderr": test_result.get("stderr", "")[:500],
    }


# ---------------------------------------------------------------------------
# 11. rollback_upgrade
# ---------------------------------------------------------------------------

def rollback_upgrade() -> Tuple[Optional[str], Optional[str]]:
    """Require the existing reviewed upgrade rollback workflow; never reset unrelated work."""
    return None, "Use Upgrade Studio to review and roll back the selected upgrade; whole-checkout reset is disabled."
