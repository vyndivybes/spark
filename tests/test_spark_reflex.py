import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_reflex import reflex_plan, reflex_execute

class FakePC:
    def __init__(self, allowed=True, success=True):
        self.allowed = allowed
        self.success = success
        self.calls = []
    def enabled(self):
        return self.allowed
    def execute(self, data):
        self.calls.append(data)
        return {'ok': self.success, 'pid': 19} if self.success else {'ok': False, 'error': 'launch failed'}

class ReflexTests(unittest.TestCase):
    def test_exact_help_has_no_pc_dependency(self):
        self.assertTrue(reflex_execute(' Reflex  Help ')["ok"])
        self.assertEqual(reflex_execute('reflex help')["execution"], "none")
    def test_launch_routes_only_to_existing_pc_access(self):
        pc = FakePC()
        result = reflex_execute('OPEN   CALCULATOR', pc)
        self.assertTrue(result['ok'])
        self.assertEqual(pc.calls, [{'action':'launch','path':'calc.exe','arguments':[]}])
    def test_disabled_fails_closed(self):
        pc = FakePC(False)
        self.assertFalse(reflex_execute('open notepad', pc)['ok'])
        self.assertEqual(pc.calls, [])
    def test_unrecognized_and_injection_fails_closed(self):
        for command in ('open calculator; remove everything', 'open cmd', 'open powershell',
                        'open notepad && echo hi', 'open notepad\nexit', 'open https://test.com',
                        'open calculator.exe', '', 'A'*121, None, 'opén calculator'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                reflex_plan(command)
    def test_failure_not_reported_as_success(self):
        pc = FakePC(success=False)
        result = reflex_execute('open notepad', pc)
        self.assertFalse(result['ok'])
        self.assertEqual(result['result']['error'], 'launch failed')
    def test_no_pc_for_help(self):
        pc = FakePC()
        self.assertEqual(reflex_execute('reflex help', pc)['kind'], 'help')
        self.assertFalse(pc.calls)

if __name__ == '__main__':
    unittest.main()
