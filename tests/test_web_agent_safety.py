"""Guard against unsafe automatic acknowledgements in the browser agent."""
import ast
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "backend" / "web_agent.py").read_text(encoding="utf-8")

class BrowserSafetyTests(unittest.TestCase):
    def test_parse(self):
        ast.parse(SOURCE)

    def test_never_auto_approve(self):
        self.assertNotIn('Auto-acknowledging to proceed.', SOURCE)
        self.assertNotIn('result_data["safety_acknowledgement"] = True', SOURCE)

    def test_sensitive_action_denied_before_navigation(self):
        function = SOURCE.split('async def execute_function_calls', 1)[1].split('async def get_function_responses', 1)[0]
        self.assertIn('decision.get("decision") == "require_confirmation"', function)
        self.assertIn('"error": "Action requires human approval;', function)
        self.assertLess(function.index('decision.get("decision")'), function.index('if fn_name == "open_web_browser"'))

if __name__ == "__main__":
    unittest.main()
