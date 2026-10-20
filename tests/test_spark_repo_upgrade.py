import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_evolution import Evolution
from spark_maintenance import MaintenanceError
from spark_repo_upgrade import snapshot
from spark_workspace import SparkWorkspace


class RepositoryUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / 'reference'
        self.reference.mkdir()
        (self.reference / 'README.md').write_text('Use a bounded cache for repeated computations.', encoding='utf-8')
        (self.reference / 'cache.py').write_text('def calculate(x):\n    return x * 2\n', encoding='utf-8')
        self.spark = self.root / 'spark'
        (self.spark / 'backend').mkdir(parents=True)
        (self.spark / 'tests').mkdir()
        self.target = self.spark / 'backend' / 'calculator.py'
        self.target.write_text('def calculate(x):\n    return x\n', encoding='utf-8')
        (self.spark / 'tests' / 'test_spark_calculator.py').write_text(
            'import sys, unittest\nfrom pathlib import Path\n'
            "sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))\n"
            'from calculator import calculate\nclass CalculationTests(unittest.TestCase):\n'
            ' def test_result(self):self.assertEqual(calculate(3),6)\n', encoding='utf-8')
        self.workspace = SparkWorkspace(self.root / 'workspace')
        self.contexts = []
        self.bad_evidence = False
        self.bad_patch = False

        async def generate(instruction, context):
            self.contexts.append(context)
            if 'spark_sources' in context:
                original = context['spark_sources'][0]
                return {'changes': [{**original, 'content': 'def calculate(x):\n    return x * 2\n',
                                     'path': 'backend/server.py' if self.bad_patch else original['path']}]}
            return {'summary': 'The sample suggests doubling calculations.', 'opportunities': [{
                'title': 'Double the result', 'rationale': 'The sampled function doubles the input.',
                'evidence': ['missing.py' if self.bad_evidence else 'cache.py'],
                'spark_paths': ['backend/calculator.py'],
                'verification': 'calculate(3) must equal 6.'}]}

        self.engine = Evolution(self.workspace, repository=self.spark, generator=generate)

    async def analyze(self):
        return await self.engine.execute('analyze_repository', 'general', {
            'repository': str(self.reference), 'goal': 'Improve calculation behavior',
            'reference_paths': ['README.md', 'cache.py']})

    async def test_analysis_stage_real_regression_activation_and_rollback(self):
        report = await self.analyze()
        self.assertEqual(report['status'], 'analyzed')
        self.assertEqual(len(report['sources']), 2)
        saved = await self.engine.execute('list_repository_analyses', 'general', {})
        self.assertEqual(saved[0]['id'], report['id'])
        reread = await self.engine.execute('read_repository_analysis', 'general', {'id': report['id']})
        self.assertEqual(reread, report)
        # Stage uses retained evidence even if the reference checkout changes.
        (self.reference / 'cache.py').write_text('raise RuntimeError("never execute me")')
        candidate = await self.engine.execute('stage_repository_upgrade', 'general', {
            'analysis_id': report['id'], 'opportunity': 0})
        self.assertEqual(candidate['status'], 'staged')
        self.assertEqual(candidate['provenance']['analysis_id'], report['id'])
        self.assertIn('return x * 2', self.contexts[-1]['reference_sources'][1]['content']
                      if len(self.contexts[-1]['reference_sources']) > 1 else self.contexts[-1]['reference_sources'][0]['content'])
        self.assertEqual(self.target.read_text(), 'def calculate(x):\n    return x\n')
        with self.assertRaises(MaintenanceError):
            await self.engine.execute('activate_repair_candidate', 'general', {'id': candidate['id'], 'approved': True})
        tested = await self.engine.execute('test_repair_candidate', 'general', {'id': candidate['id'], 'approved': True})
        self.assertEqual(tested['status'], 'tested')
        applied = await self.engine.execute('activate_repair_candidate', 'general', {'id': candidate['id'], 'approved': True})
        self.assertIn('return x * 2', self.target.read_text())
        await self.engine.execute('rollback_repair', 'general', {'id': applied['id']})
        self.assertEqual(self.target.read_text(), 'def calculate(x):\n    return x\n')

    async def test_invalid_model_evidence_and_patch_scope_are_rejected(self):
        self.bad_evidence = True
        with self.assertRaisesRegex(MaintenanceError, 'unsupported evidence'):
            await self.analyze()
        self.assertEqual(self.engine.repositories.list('general'), [])
        self.bad_evidence = False
        report = await self.analyze()
        self.bad_patch = True
        with self.assertRaisesRegex(MaintenanceError, 'exceeded'):
            await self.engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})
        self.assertEqual(self.engine.maintenance.candidates(), [])

    async def test_project_isolation_invalid_selection_and_stale_source(self):
        report = await self.analyze()
        with self.assertRaises(MaintenanceError):
            self.engine.repositories.read('other', report['id'])
        for index in (-1, 4, True, '0'):
            with self.assertRaises(MaintenanceError):
                await self.engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': index})
        candidate = await self.engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})
        self.target.write_text('value = 42\n')
        with self.assertRaisesRegex(MaintenanceError, 'Source changed'):
            await self.engine.execute('test_repair_candidate', 'general', {'id': candidate['id'], 'approved': True})
        self.assertEqual(self.target.read_text(), 'value = 42\n')

    async def test_snapshot_excludes_secrets_dependencies_binary_and_large_files(self):
        for name in ('settings.json', 'credentials.json', '.env', 'access_token.py'):
            (self.reference / name).write_text('private')
        (self.reference / 'node_modules').mkdir()
        (self.reference / 'node_modules' / 'library.js').write_text('private')
        (self.reference / 'large.py').write_bytes(b'x' * 65537)
        (self.reference / 'binary.py').write_bytes(b'\x00bad')
        evidence = snapshot(str(self.reference), [])
        self.assertEqual({s['path'] for s in evidence['sources']}, {'README.md', 'cache.py'})
        self.assertEqual(set(evidence['skipped']), {'large.py', 'binary.py'})
        for selected in (['../outside.py'], ['settings.json'], ['cache.py', 'cache.py']):
            with self.assertRaises(MaintenanceError):
                snapshot(str(self.reference), selected)
        with self.assertRaises(MaintenanceError):
            snapshot('https://github.com/example/repo', [])

    async def test_snapshot_does_not_follow_directory_links(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'private.py').write_text('private')
        try:
            (self.reference / 'linked').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Creating directory symlinks requires host privileges.')
        self.assertNotIn('linked/private.py', snapshot(str(self.reference), [])['inventory'])


if __name__ == '__main__':
    unittest.main()
