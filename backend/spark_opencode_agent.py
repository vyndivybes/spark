"""Capability 04 — Native OpenCode agent for SPARK on Windows.

Discovers an *installed* OpenCode CLI on the host, runs headless sessions in
a scoped working directory, captures session output with credential masking,
extracts the resulting git patch for human review, and runs only approved,
allow-listed test commands inside the same scope. Merging, deploying or
executing arbitrary shell commands require explicit owner approval; nothing
is applied automatically. OpenCode keeps the user's own configured provider;
SPARK never provisions one.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

MAX_OUTPUT = 400_000
MAX_DIFF = 120_000
TEST_COMMAND_PREFIXES = ("python -m pytest", "python -m unittest", "pytest", "node --test",
                         "npm test", "git --version")
SECRET_PATTERNS = re.compile(
    r"([A-Za-z0-9_]*(?:api_key|apikey|token|secret|password|authorization)[A-Za-z0-9_]*)"
    r"\s*[=:]\s*[\"']?\S[^\s\"']*", re.I)


class OpenCodeError(ValueError):
    """Invalid request, missing binary or refused operation."""


def mask_secrets(text):
    """Replace assignment-style secret values with a redaction marker."""
    if not isinstance(text, str):
        return ""
    return SECRET_PATTS.sub(lambda match: match.group(1) + "=<redacted>", text)


SECRET_PATTS = SECRET_PATTERNS


def discover_opencode(*, finder=shutil.which, version_runner=None):
    """Report the installed OpenCode CLI; never claims a feature is live."""
    exe = finder("opencode") or finder("opencode.exe") or finder("opencode.cmd")
    version = None
    if exe and version_runner:
        try:
            code, out, _ = version_runner([str(exe), "--version"], 15)
            if code == 0:
                version = out.strip()[:40]
        except (OSError, subprocess.TimeoutExpired):
            version = None
    return {"binary": str(exe) if exe else None,
            "installed": bool(exe),
            "version": version,
            "status": "installed" if exe else "not_configured",
            "message": ("Ready for headless sessions." if exe else
                        "OpenCode is not installed on this machine. Install it "
                        "manually first; SPARK will not download binaries.")}


class OpenCodeAgent:
    """Bounded headless OpenCode sessions with review and test gates."""

    def __init__(self, root, *, runner=None):
        self.root = Path(root).resolve()
        discovery = discover_opencode()
        self.binary = discovery["binary"]
        self.installed = discovery["installed"]
        self._runner = runner
        self.sessions = {}   # session_id -> dict(cwd, prompt, started, state, transcript)
        self.next_id = 0

    # -- session ----------------------------------------------------------
    def run(self, prompt, *, cwd=None, timeout=300):
        """Start and await one headless session; output is captured, masked."""
        if not isinstance(prompt, str) or not 10 <= len(prompt) <= 4000:
            raise OpenCodeError("Write a session prompt of 10-4000 characters.")
        workdir = self._scoped_dir(cwd)
        # Applied only on the real execution path: an injected runner is a
        # simulation transport, so the installed-binary gate must not depend
        # on what is (or is not) installed on the test host.
        if self._runner is None and not self.installed:
            raise OpenCodeError("OpenCode is not installed on this machine.")
        command = [self.binary, "run", prompt]
        started = time.time()
        code, out, err = self._run(command, workdir, timeout)
        transcript = mask_secrets((out or "") + "\n" + (err or ""))
        if len(transcript) > MAX_OUTPUT:
            transcript = transcript[:MAX_OUTPUT] + "\n...[truncated]"
        session = {"id": self._start_session_id(),
                   "cwd": str(workdir), "prompt": prompt,
                   "started": started, "exit_code": code,
                   "state": "completed", "transcript": transcript}
        self.sessions[session["id"]] = session
        return session

    def _start_session_id(self):
        self.next_id += 1
        return "s-" + str(self.next_id)

    def _scoped_dir(self, cwd):
        target = Path(cwd).resolve() if cwd else self.root
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise OpenCodeError("Session work directory must stay inside the "
                                "approved repository root.") from error
        if not target.is_dir():
            raise OpenCodeError("Session work directory must be an existing folder.")
        return target

    def _run(self, command, cwd, timeout):
        cwd = str(cwd)
        if self._runner:
            return self._runner(command, cwd, timeout)
        try:
            result = subprocess.run(command, cwd=str(cwd), timeout=timeout,
                                    capture_output=True, text=True, encoding="utf-8",
                                    errors="replace")
            return result.returncode, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired as expired:
            partial = (expired.stdout or b"") if isinstance(expired.stdout, bytes) else (expired.stdout or "")
            message = mask_secrets(str(partial) + "\n[timeout] session cancelled after %ss" % timeout)
            return 124, message, ""

    # -- patch review -----------------------------------------------------
    def diff(self, session=None, *, git_runner=None):
        """Capture the git patch produced in the scoped directory."""
        workdir = str(self._resolve_session(session)) if session else str(self.root)
        runner = git_runner or self._run
        code, out, err = runner(["git", "status", "--porcelain"], workdir, 30)
        if code != 0:
            raise OpenCodeError("git status failed; is this a git work tree? "
                                + str(err)[:200])
        code, full, _ = runner(["git", "diff"], workdir, 30)
        if code != 0:
            raise OpenCodeError("git diff failed. " + str(err)[:200])
        patch = mask_secrets(full or "")
        if len(patch) > MAX_DIFF:
            patch = patch[:MAX_DIFF] + "\n...[truncated]"
        changed = mask_secrets(out or "")
        return {"patch": patch, "changed_entries": changed.splitlines(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "masked_secrets": True}

    def _resolve_session(self, session_id):
        if session_id is None:
            return self.root
        record = self.sessions.get(str(session_id))
        if not record:
            raise OpenCodeError("Unknown session; start one first.")
        return Path(record["cwd"])

    # -- approved tests ---------------------------------------------------
    def run_tests(self, test_command, *, cwd=None, timeout=600):
        """Run an allow-listed test command inside the scoped directory."""
        if not isinstance(test_command, str):
            raise OpenCodeError("Provide a test command string.")
        allowed = any(test_command.strip().startswith(prefix)
                      for prefix in TEST_COMMAND_PREFIXES)
        if not allowed:
            raise OpenCodeError("Only bounded test commands may run: "
                                + ", ".join(TEST_COMMAND_PREFIXES))
        workdir = self._scoped_dir(cwd)
        parts = test_command.strip().split()
        code, out, err = self._run(parts, workdir, timeout)
        text = mask_secrets((out or "") + "\n" + (err or ""))
        return {"command": test_command, "exit_code": code, "state": "completed",
                "output": text[:MAX_OUTPUT], "cwd": str(workdir)}

    # -- status -----------------------------------------------------------
    def status(self):
        """Honest readiness for this host; no installed check is faked."""
        return {"discovery": discover_opencode(),
                "root": str(self.root),
                "sessions": {"count": len(self.sessions),
                             "latest": self._latest_summary()},
                "policy": ("scoped cwd, masked output, human patch review, "
                           "allow-listed tests; no merge/deploy without approval")}

    def _latest_summary(self):
        if not self.sessions:
            return None
        latest = max(self.sessions.values(), key=lambda s: s["started"])
        return {"id": latest["id"], "state": latest["state"],
                "exit_code": latest["exit_code"],
                "cwd": latest["cwd"],
                "transcript_preview": latest["transcript"][:600]}
