from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_workspace import SparkWorkspace
from spark_workbench import Workbench
from spark_intelligence.models import Models


class LocalTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_capture_probes_and_measures_without_cloud_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            workbench = Workbench(SparkWorkspace(Path(directory)))
            workbench.telemetry.sampler = None
            calls = []

            async def request(identifier, path, body=None):
                calls.append((path, body))
                if path == '/api/tags':
                    return {'models': [{'name': 'gemma3:1b'}]}
                return {'response': '42', 'prompt_eval_count': 12, 'eval_count': 2}

            workbench.intelligence.models = Models(config={'local': {
                'provider': 'ollama', 'model': 'gemma3:1b',
                'base_url': 'http://127.0.0.1:11434', 'context': 4096}})
            workbench.intelligence.models._request = request
            result = await workbench.execute('telemetry_capture', 'default', {
                'model': 'local', 'prompt': 'Return 42', 'allow_cloud': False})
            self.assertTrue(result['recorded'])
            self.assertEqual(calls[0][0], '/api/tags')
            self.assertEqual(calls[1][0], '/api/generate')
            aggregate = workbench.telemetry.aggregate('local')[0]
            self.assertEqual(aggregate['output_tokens_total'], 2)

    async def test_cloud_without_consent_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            workbench = Workbench(SparkWorkspace(Path(directory)))
            workbench.intelligence.models = Models(config={'cloud': {
                'provider': 'groq', 'model': 'example', 'context': 4096}})

            async def request(*args, **kwargs):
                self.fail('Cloud must be refused before a provider call')

            workbench.intelligence.models._request = request
            with self.assertRaisesRegex(ValueError, 'consent'):
                await workbench.execute('telemetry_capture', 'default', {
                    'model': 'cloud', 'prompt': 'ping', 'allow_cloud': False})


if __name__ == '__main__':
    unittest.main()
