"""Offline regression checks: no credentials, no real API calls."""
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "spark_gemini_preflight.py"
spec = importlib.util.spec_from_file_location("spark_gemini_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GeminiPreflightTests(unittest.TestCase):
    def test_environment_precedes_file(self):
        with tempfile.TemporaryDirectory() as d, patch.dict("os.environ", {"GEMINI_API_KEY": "example"}, clear=True):
            self.assertEqual(module.read_key(d), ("example", "environment"))

    def test_arkus_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "arkus").mkdir()
            (root / "arkus" / "config.json").write_text(json.dumps({"api_key": "secret-test"}))
            with patch.dict("os.environ", {"APPDATA": d}, clear=True):
                self.assertEqual(module.read_key(root)[0], None)
                self.assertEqual(module.read_key(root, allow_arkus=True), ("secret-test", "ARKUS opt-in"))

    def test_status_mapping(self):
        self.assertIn("quota", module.classify_http(429).lower())
        self.assertIn("Authentication", module.classify_http(401))

    def test_probe_does_not_echo_secret(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, *args):
                return b'{"models":[{"name":"models/gemini-3.8-live"}]}'
        with patch.object(module.urllib.request, "urlopen", return_value=Response()):
            self.assertEqual(module.probe("secret-test")["state"], "model_visible")
            result = str(module.probe("secret-test"))
            self.assertNotIn("secret-test", result)


if __name__ == "__main__":
    unittest.main()
