"""Exercise copied OpenJarvis discovery through Spark's real provider gateway."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_trace_learning import TraceLearning
from spark_python_tools import GeneratedToolGateway


class LearningTests(unittest.TestCase):
    def test_persistence_threshold_failure_and_project_isolation(self):
        with tempfile.TemporaryDirectory() as root:
            learning = TraceLearning(root)
            for _ in range(2):
                learning.record('default', ['read', 'summarize'], True)
            self.assertEqual(learning.patterns('default'), [])
            learning.record('default', ['read', 'summarize'], True)
            found = TraceLearning(root).patterns('default')
            self.assertEqual(found[0]['frequency'], 3)
            self.assertTrue(found[0]['advisory'])
            self.assertEqual(learning.patterns('other'), [])
            learning.record('default', ['read', 'summarize'], False)
            self.assertEqual(learning.patterns('default'), [])
            with self.assertRaises(ValueError):
                learning.record('../outside', ['read'], True)

    def test_gateway_records_runs_and_exposes_only_active_workflows(self):
        async def exercise(root):
            rows = [{'name': n, 'description': n, 'id': n, 'status': 'active',
                     'tests': [{'inputs': {'private': 'never retained'}}]} for n in ['read', 'summarize']]
            evolution = SimpleNamespace(
                trace_learning=TraceLearning(root),
                python_tools=SimpleNamespace(policy=lambda: {'enabled': True}, list=lambda p: rows),
                execute=AsyncMock(return_value={'result': 'private-result'}))
            gateway = GeneratedToolGateway(evolution, 'default')
            for _ in range(3):
                for name in ['read', 'summarize']:
                    result = await gateway.call({'action': 'run', 'name': name,
                                                 'input_json': '{"private":"private-input"}'})
                    self.assertTrue(result['ok'])
            result = await gateway.call({'action': 'list'})
            self.assertIn(['read', 'summarize'], [p['tool_sequence'] for p in result['learned_workflows']])
            stored = (Path(root) / 'trace-learning/default.json').read_text()
            self.assertNotIn('private', stored)
            rows[0]['status'] = 'inactive'
            self.assertEqual((await gateway.call({'action': 'list'}))['learned_workflows'], [])
            evolution.execute.side_effect = ValueError('worker failed')
            self.assertFalse((await gateway.call({'action': 'run', 'name': 'summarize'}))['ok'])
            self.assertEqual(json.loads((Path(root)/'trace-learning/default.json').read_text())[-1]['outcome'], 'failure')
        with tempfile.TemporaryDirectory() as root:
            asyncio.run(exercise(root))


if __name__ == '__main__':
    unittest.main()
