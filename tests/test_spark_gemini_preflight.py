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


    def test_probe_searches_every_model_page_before_declaring_absent(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, *args):
                return json.dumps(self.payload).encode("utf-8")

        replies = [
            Response({"models": [{"name": "models/gemini-3.8-flash"}], "nextPageToken": "page-two"}),
            Response({"models": [{"name": "models/gemini-3.8-live"}]}),
        ]
        requests = []
        def fake_open(request, timeout):
            requests.append(request)
            return replies.pop(0)
        with patch.object(module.urllib.request, "urlopen", side_effect=fake_open):
            result = module.probe("secret-test")
        self.assertEqual(result["state"], "model_visible")
        self.assertEqual(result["listed_models"], 2)
        self.assertEqual(len(requests), 2)
        self.assertIn("pageToken=page-two", requests[1].full_url)
        self.assertEqual(requests[0].get_header("X-goog-api-key"), "secret-test")
        self.assertNotIn("secret-test", str(result))

    def test_probe_reports_absent_only_after_final_page(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, *args):
                return b'{"models":[{"name":"models/gemini-3.8-flash"}]}'
        with patch.object(module.urllib.request, "urlopen", return_value=Response()):
            result = module.probe("secret-test")
        self.assertEqual(result["state"], "model_not_listed")
        self.assertIn("gemini-3.8-flash", result["available_models"])


if __name__ == "__main__":
    unittest.main()
