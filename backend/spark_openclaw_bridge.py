"""Local OpenClaw Rex CLI bridge with a fail-closed free-model policy."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]*/[A-Za-z0-9][A-Za-z0-9._:/-]{0,110}$")
SECRET = re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|secret|password|authorization)\s*[:=]\s*)[\"']?[^\s,\"'}]+")
BEARER = re.compile(r"(?i)\bbearer\s+\S+")


class OpenClawError(ValueError):
    """Refused or unavailable OpenClaw operation."""


def redact(value):
    if not isinstance(value, str):
        return ""
    return BEARER.sub("Bearer [redacted]",
                      SECRET.sub(lambda m: m.group(1) + "[redacted]", value))


class OpenClawBridge:
    """One Rex turn via the existing Gateway; never installs or edits OpenClaw.

    The exact free-tier model allowlist is empty until set by the owner.
    The model is pinned per turn. OpenClaw's explicit --model selection
    prevents its configured fallback chain from selecting a paid model.
    """

    def __init__(self, *, runner=None, binary=None):
        self.binary = binary if binary is not None else shutil.which("openclaw")
        self.runner = runner
        self.lock = threading.Lock()

    @staticmethod
    def approved_models():
        models = (s.strip() for s in os.getenv("SPARK_OPENCLAW_FREE_MODELS", "").split(","))
        return list(dict.fromkeys(s for s in models if MODEL_ID.fullmatch(s)))

    def _call(self, args, timeout):
        if self.runner is not None:
            return self.runner([self.binary or "openclaw", *args], timeout)
        if not self.binary:
            raise OpenClawError("OpenClaw CLI not found in Windows PATH.")
        try:
            proc = subprocess.run([self.binary, *args], timeout=timeout,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", shell=False)
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            raise OpenClawError(
                "Rex timed out. Gateway may still be processing; inspect the session before retry."
            ) from exc
        except OSError as exc:
            raise OpenClawError("OpenClaw failed to start on this host.") from exc

    def status(self):
        """Gateway reachability never implies operator authorization."""
        approved = self.approved_models()
        if not self.binary and self.runner is None:
            return {"installed": False, "state": "not_installed", "gateway": "unavailable",
                    "agent": "rex", "operator_verified": False,
                    "approved_free_models": approved}
        try:
            code, _, _ = self._call(["gateway", "status", "--json", "--require-rpc"], 12)
        except OpenClawError:
            code = 1
        gateway = "responding" if code == 0 else "unavailable"
        state = ("ready_to_test" if code == 0 and approved else
                 "model_approval_required" if code == 0 else "gateway_unavailable")
        return {"installed": True, "state": state, "gateway": gateway,
                "agent": "rex", "operator_verified": False,
                "approved_free_models": approved,
                "note": "Only a successful Rex turn verifies operator scope."}

    def run(self, prompt, model, timeout=120):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 3000:
            raise OpenClawError("Enter a prompt of 1-3000 characters.")
        if not isinstance(model, str) or model not in self.approved_models():
            raise OpenClawError(
                "Model not approved by SPARK_OPENCLAW_FREE_MODELS. Verify a zero-billed model first."
            )
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 10 <= timeout <= 300:
            raise OpenClawError("Timeout must be 10-300 seconds.")
        if not self.binary and self.runner is None:
            raise OpenClawError("OpenClaw CLI not installed.")
        if not self.lock.acquire(blocking=False):
            raise OpenClawError("Another Rex request is active.")
        try:
            # Prompt text is never added to shell/command-line arguments.
            with tempfile.TemporaryDirectory(prefix="spark-rex-") as folder:
                message_file = Path(folder) / "message.txt"
                with message_file.open("x", encoding="utf-8") as fh:
                    fh.write(prompt)
                try:
                    os.chmod(message_file, 0o600)
                except OSError:
                    pass
                args = ["agent", "--agent", "rex", "--session-key", "spark-rex",
                        "--model", model, "--message-file", str(message_file),
                        "--timeout", str(timeout), "--json"]
                code, output, _ = self._call(args, timeout + 20)
            if code != 0:
                raise OpenClawError(
                    "Rex turn failed (exit " + str(code) +
                    "). Check Gateway, operator scope, Rex auth and free quota."
                )
            if len(output) > 1_000_000:
                raise OpenClawError("Rex returned excessive data.")
            try:
                envelope = json.loads(output)
            except (ValueError, TypeError) as exc:
                raise OpenClawError("Rex did not return JSON.") from exc
            if not isinstance(envelope, dict):
                raise OpenClawError("Invalid Rex result.")
            result = envelope.get("result", envelope)
            if not isinstance(result, dict):
                raise OpenClawError("Invalid Rex result envelope.")
            if result.get("status") in ("error", "timeout", "in_flight"):
                raise OpenClawError("Rex status " + result["status"] +
                                    "; inspect the session before retry.")
            payloads = result.get("payloads") or []
            answer = " ".join(str(item.get("text", "")) for item in payloads
                              if isinstance(item, dict)).strip()
            if not answer:
                answer = str(result.get("final") or "").strip()
            if not answer:
                raise OpenClawError("Rex returned no answer.")
            return {"state": "completed", "operator_verified": True,
                    "agent": "rex", "model": model,
                    "response": redact(answer)[:12000],
                    "truncated": len(answer) > 12000}
        finally:
            self.lock.release()
