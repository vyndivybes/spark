import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_evaluations import Evaluations, EvaluationError
from spark_intelligence.models import Models
from spark_model_evaluations import attach_local_evaluator


class ModelEvaluationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.evaluations = Evaluations(self.directory.name)
        self.models = Models(config={'local': {
            'provider': 'ollama', 'model': 'gemma3:1b',
            'base_url': 'http://127.0.0.1:11434', 'context': 4096}})
        self.requests = []

        async def request(identifier, path, body=None):
            self.requests.append((path, body))
            if path == '/api/tags':
                return {'models': [{'name': 'gemma3:1b'}]}
            return {'response': '"wrong answer"'}
        self.models._request = request

    def test_model_failure_is_measured_without_copying_expected_answers(self):
        attached = attach_local_evaluator(self.evaluations, self.models, 'local')
        report = self.evaluations.run(attached['name'], 'memory_retrieval')
        self.assertEqual(report['total'], 2)
        self.assertEqual(report['passed'], 0)
        self.assertIn('local model:gemma3:1b', report['provenance'])
        for path, body in self.requests:
            if path == '/api/generate':
                self.assertNotIn('"expected"', body['prompt'])
                self.assertNotIn('"id"', body['prompt'])
        self.assertEqual(self.requests[0][0], '/api/tags')

    def test_cloud_and_unknown_models_are_refused_before_request(self):
        for identifier in ('unknown', 'cloud'):
            self.models.config['cloud'] = {'provider': 'gemini', 'model': 'example', 'context': 4096}
            with self.assertRaises(EvaluationError):
                attach_local_evaluator(self.evaluations, self.models, identifier)
        self.assertEqual(self.requests, [])

    def test_model_text_cannot_execute_as_python(self):
        async def malicious(*args, **kwargs):
            return {'answer': '__import__("os").getcwd()'}
        self.models.health['local'] = {'available': True, 'state': 'healthy'}
        self.models.generate = malicious
        attached = attach_local_evaluator(self.evaluations, self.models, 'local')
        report = self.evaluations.run(attached['name'], 'memory_retrieval')
        self.assertEqual(report['passed'], 0)
        self.assertTrue(all('runner error' in failure['reason'] for failure in report['failures']))

    def test_complete_json_block_and_answer_wrapper_are_scored(self):
        async def formatted(*args, **kwargs):
            return {'answer': '```json\n{"answer":"not_stored"}\n```'}
        self.models.health['local'] = {'available': True, 'state': 'healthy'}
        self.models.generate = formatted
        attached = attach_local_evaluator(self.evaluations, self.models, 'local')
        report = self.evaluations.run(attached['name'], 'memory_retrieval')
        self.assertEqual(report['passed'], 1)
        self.assertEqual(report['failures'][0]['id'], 'memory-exact')


if __name__ == '__main__':
    unittest.main()
