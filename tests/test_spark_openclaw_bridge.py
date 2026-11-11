"""No-cost OpenClaw Rex adapter tests, with a fake CLI (no network calls)."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_openclaw_bridge import OpenClawBridge, OpenClawError

FREE = "openrouter/example:free"


class OpenClawBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def runner(args, timeout):
            self.calls.append((args, timeout))
            if args[1:3] == ["gateway", "status"]:
                return 0, '{"ok":true}', ""
            self.assertIn("--message-file", args)
            path = Path(args[args.index("--message-file") + 1])
            self.assertEqual(path.read_text(encoding="utf-8"), "health check & echo")
            return 0, json.dumps({"payloads": [{"text": "Rex is running."}]}), ""
        self.adapter = OpenClawBridge(runner=runner, binary="openclaw")

    def test_status_does_not_claim_operator(self):
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": ""}):
            status = self.adapter.status()
        self.assertFalse(status["operator_verified"])
        self.assertEqual(status["state"], "model_approval_required")

    def test_rejects_unapproved_model_without_execution(self):
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": FREE}):
            with self.assertRaises(OpenClawError):
                self.adapter.run("health check & echo", "openai/paid-model")
        self.assertFalse(self.calls)

    def test_fail_closed_when_allowlist_empty(self):
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": ""}):
            with self.assertRaises(OpenClawError):
                self.adapter.run("health check & echo", FREE)
        self.assertFalse(self.calls)

    def test_success_has_no_delivery_and_uses_private_file(self):
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": FREE}):
            out = self.adapter.run("health check & echo", FREE, 30)
        self.assertEqual(out["state"], "completed")
        self.assertEqual(out["response"], "Rex is running.")
        cmd, timeout = self.calls[0]
        self.assertEqual(cmd[1:4], ["agent", "--agent", "rex"])
        self.assertIn("--model", cmd)
        self.assertNotIn("--deliver", cmd)
        self.assertNotIn("--local", cmd)
        self.assertNotIn("health check & echo", " ".join(cmd))
        self.assertEqual(timeout, 50)
        self.assertFalse(Path(cmd[cmd.index("--message-file") + 1]).exists())

    def test_fails_without_leaking_stderr_secret(self):
        def reject(args, timeout):
            self.calls.append((args, timeout))
            return 1, "", "Authorization: Bearer supersecret"
        self.adapter.runner = reject
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": FREE}):
            with self.assertRaisesRegex(OpenClawError, "operator scope"):
                self.adapter.run("health check & echo", FREE)
        self.assertEqual(len(self.calls), 1)

    def test_refuses_bad_timeouts(self):
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": FREE}):
            for bad in (0, 301, True, "30"):
                with self.assertRaises(OpenClawError):
                    self.adapter.run("health check & echo", FREE, bad)
        self.assertFalse(self.calls)

    def test_empty_output_is_not_success(self):
        self.adapter.runner = lambda cmd, timeout: (0, "{}", "")
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": FREE}):
            with self.assertRaisesRegex(OpenClawError, "no answer"):
                self.adapter.run("health check & echo", FREE)

    def test_missing_cli_not_operational(self):
        self.assertEqual(OpenClawBridge(binary="").status()["state"], "not_installed")

    def test_malformed_json_rejected(self):
        self.adapter.runner = lambda cmd, timeout: (0, "broken", "")
        with patch.dict(os.environ, {"SPARK_OPENCLAW_FREE_MODELS": FREE}):
            with self.assertRaisesRegex(OpenClawError, "JSON"):
                self.adapter.run("health check & echo", FREE)


if __name__ == "__main__":
    unittest.main()
