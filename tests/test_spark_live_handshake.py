"""Offline regression tests for a single isolated SPARK Live handshake."""
import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

script = Path(__file__).resolve().parents[1] / "scripts" / "spark_live_handshake.py"
spec = importlib.util.spec_from_file_location("spark_live_handshake", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeLive:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
    def connect(self, model, config):
        self.calls.append({"model": model, "config": config})
        owner = self
        class Session:
            async def __aenter__(self):
                if owner.error:
                    raise owner.error
                return self
            async def __aexit__(self, exc_type, exc, tb):
                return False
        return Session()

class MinimalLiveHandshakeTests(unittest.TestCase):
    def test_minimal_config_has_no_tools_or_audio_access(self):
        live = FakeLive()
        class Obj: pass
        client = Obj()
        client.aio = Obj()
        client.aio.live = live
        result = asyncio.run(module.connect_once(client, "gemini-3.8-live"))
        self.assertEqual(result["state"], "connected")
        self.assertEqual(live.calls, [
            {"model": "gemini-3.8-live", "config": {"response_modalities": ["AUDIO"]}}
        ])

    def test_quota_errors_are_classified_without_leaking_secret(self):
        error = RuntimeError("HTTP 429 RESOURCE_EXHAUSTED key=AIzaSecretXX quota not available")
        result = module.classify_error(error)
        self.assertEqual(result["state"], "rejected")
        self.assertEqual(result["category"], "quota_or_rate_limit")
        self.assertEqual(result["http_status"], 429)
        self.assertNotIn("AIzaSecretXX", str(result))

    def test_validation_error_is_not_blindly_labeled_quota(self):
        result = module.classify_error(RuntimeError("HTTP 400 Invalid argument: tools"))
        self.assertEqual(result["category"], "invalid_request")
        self.assertEqual(result["http_status"], 400)

    def test_invalid_model_name_is_rejected_without_network(self):
        self.assertEqual(module.validate_model("gemini-3.8-live"), "gemini-3.8-live")
        with self.assertRaises(ValueError):
            module.validate_model("models/shell-command")

if __name__ == "__main__":
    unittest.main()
