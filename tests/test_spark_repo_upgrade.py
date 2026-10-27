import hashlib
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
from spark_repo_import import RepoImportError
from unittest.mock import patch
from unittest.mock import AsyncMock


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
        self.cite_spark = False

        async def generate(instruction, context):
            self.contexts.append(context)
            if 'reference_sources' in context:
                original = context['spark_sources'][0]
                return {'patches': [{'path': 'backend/server.py' if self.bad_patch else original['path'],
                                    'sha256': original['sha256'],
                                    'edits': [{'old': 'return x', 'new': 'return x * 2'}]}]}
            return {'summary': 'The sample suggests doubling calculations.', 'opportunities': [{
                'title': 'Double the result', 'rationale': 'The sampled function doubles the input.',
                'evidence': (['missing.py' if self.bad_evidence else 'cache.py']
                             + (['backend/calculator.py'] if self.cite_spark else [])),
                'spark_paths': ['backend/calculator.py'],
                'verification': 'calculate(3) must equal 6.'}]}

        self.engine = Evolution(self.workspace, repository=self.spark, generator=generate)

    async def analyze(self):
        return await self.engine.execute('analyze_repository', 'general', {
            'repository': str(self.reference), 'goal': 'Improve calculation behavior',
            'reference_paths': ['README.md', 'cache.py']})

    async def test_analysis_compares_real_spark_source_instead_of_only_target_names(self):
        (self.spark / 'backend' / 'aaa_unrelated.py').write_text('unrelated = True\n')
        report = await self.analyze()
        supplied = {s['path']: s for s in self.contexts[-1]['spark_sources']}
        self.assertIn('backend/calculator.py', supplied)
        self.assertIn('return x', supplied['backend/calculator.py']['content'])
        self.assertIn('backend/calculator.py', report['analysis_sample']['spark_targets'])

    async def test_analysis_accepts_citations_to_both_compared_implementations(self):
        self.cite_spark = True
        report = await self.analyze()
        self.assertEqual(report['opportunities'][0]['evidence'], ['cache.py', 'backend/calculator.py'])

    async def test_explicit_spark_target_wins_over_high_scoring_unrelated_modules(self):
        for name in ('spark_retry_queue.py', 'spark_retry_recovery.py'):
            (self.spark / 'backend' / name).write_text(
                '# task retry queue planning recovery error validation\nvalue = True\n')
        for requested in ('backend/calculator.py', 'BACKEND\\CALCULATOR.PY', 'calculator.py'):
            with self.subTest(requested=requested):
                report = await self.engine.execute('analyze_repository', 'general', {
                    'repository': str(self.reference),
                    'goal': f'Compare {requested}; improve task retry queue planning recovery error validation.',
                    'reference_paths': ['cache.py']})
                supplied = report['analysis_sample']['spark_sources']
                self.assertEqual([s['path'] for s in supplied], ['backend/calculator.py'])
                self.assertIn('return x', supplied[0]['content'])

    async def test_explicit_protected_or_missing_target_does_not_fall_back(self):
        (self.spark / 'backend' / 'server.py').write_text('# authorization boundary\n')
        for requested in ('backend/server.py', 'backend/missing.py'):
            with self.subTest(requested=requested), self.assertRaisesRegex(MaintenanceError, 'Requested Spark file'):
                await self.engine.execute('analyze_repository', 'general', {
                    'repository': str(self.reference), 'goal': f'Compare {requested}',
                    'reference_paths': ['cache.py']})
        self.assertEqual(self.contexts, [])

    async def test_explicit_oversized_target_is_not_silently_replaced(self):
        self.target.write_text('#' + 'x' * 65536 + '\n')
        with self.assertRaisesRegex(MaintenanceError, 'Requested Spark'):
            await self.engine.execute('analyze_repository', 'general', {
                'repository': str(self.reference), 'goal': 'Compare backend/calculator.py',
                'reference_paths': ['cache.py']})
        self.assertEqual(self.contexts, [])

    async def test_more_explicit_targets_than_fit_are_rejected_before_model_request(self):
        for name in ('first.py', 'second.py'):
            (self.spark / 'backend' / name).write_text('value = True\n')
        with self.assertRaisesRegex(MaintenanceError, 'at most two Spark'):
            await self.engine.execute('analyze_repository', 'general', {
                'repository': str(self.reference),
                'goal': 'Compare backend/calculator.py, backend/first.py and backend/second.py',
                'reference_paths': ['cache.py']})
        self.assertEqual(self.contexts, [])

    def test_default_snapshot_prefers_code_over_nested_readmes_and_includes_rst(self):
        for i in range(18):
            folder = self.reference / f'notes{i:02}'
            folder.mkdir()
            (folder / 'README.md').write_text('Overview only.\n')
        (self.reference / 'README.rst').write_text('Scheduling documentation.\n')
        sources = snapshot(str(self.reference), [])['sources']
        self.assertIn('cache.py', [s['path'] for s in sources])
        self.assertIn('README.rst', [s['path'] for s in sources])

    async def test_preview_reads_sources_without_model_or_saved_analysis(self):
        (self.reference / 'cache.py').write_text('raise RuntimeError("must not execute")')
        report = await self.engine.execute('preview_repository', 'general', {
            'repository': str(self.reference), 'reference_paths': ['cache.py']})
        self.assertEqual([s['path'] for s in report['sources']], ['cache.py'])
        self.assertIn('must not execute', report['sources'][0]['content'])
        self.assertEqual(self.contexts, [])
        self.assertEqual(self.engine.repositories.list('general'), [])

    async def test_import_failures_reach_workspace_as_actionable_errors(self):
        with patch('spark_evolution.import_evidence', side_effect=RepoImportError('Clone timed out; try a smaller repository.')):
            for action, payload in (
                ('import_repository', {'url': 'https://github.com/example/repo', 'reference_paths': []}),
                ('preview_repository', {'repository': 'https://github.com/example/repo', 'reference_paths': []}),
                ('analyze_repository', {'repository': 'https://github.com/example/repo', 'reference_paths': [], 'goal': 'Review caching'}),
            ):
                with self.subTest(action=action), self.assertRaisesRegex(MaintenanceError, 'Clone timed out'):
                    await self.engine.execute(action, 'general', payload)

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

    async def test_staged_regression_checks_can_read_application_source_dependencies(self):
        for folder, filename in (('src', 'panel.jsx'), ('electron', 'bridge.cjs')):
            (self.spark / folder).mkdir()
            (self.spark / folder / filename).write_text('/* application source */\n')
        (self.spark / 'tests' / 'test_spark_app_sources.py').write_text(
            'import unittest\nfrom pathlib import Path\n'
            'class Sources(unittest.TestCase):\n'
            ' def test_files(self):\n'
            '  root = Path(__file__).resolve().parents[1]\n'
            '  self.assertIn("application source", (root/"src"/"panel.jsx").read_text())\n'
            '  self.assertIn("application source", (root/"electron"/"bridge.cjs").read_text())\n')
        report = await self.analyze()
        candidate = await self.engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})
        tested = await self.engine.execute('test_repair_candidate', 'general', {'id': candidate['id'], 'approved': True})
        self.assertEqual(tested['status'], 'tested')

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

    async def test_default_provider_stage_uses_strict_json_and_keeps_patch_scope_checks(self):
        report = await self.analyze()
        engine = Evolution(self.workspace, repository=self.spark)
        value = {'patches': [{'path': 'backend/calculator.py',
                             'sha256': hashlib.sha256(self.target.read_bytes()).hexdigest(),
                             'edits': [{'old': 'return x', 'new': 'return x * 2'}]}]}
        reply = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}
        with patch('spark_groq.GroqClient._http', new_callable=AsyncMock, return_value=reply) as http, patch.dict('os.environ', {'GROQ_API_KEY': 'test-only'}):
            candidate = await engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})
            self.assertEqual(candidate['status'], 'staged')
            self.assertEqual(self.target.read_text(), 'def calculate(x):\n    return x\n')
            self.assertTrue(http.await_args.kwargs['body']['response_format']['json_schema']['strict'])
            value['patches'][0]['path'] = 'backend/server.py'
            reply['choices'][0]['message']['content'] = json.dumps(value)
            with self.assertRaisesRegex(MaintenanceError, 'exceeded'):
                await engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})

    async def test_model_can_decline_unsupported_goal_without_staging_a_candidate(self):
        report = await self.analyze()
        self.engine.repositories.patch_generator = AsyncMock(return_value={'patches': []})
        with self.assertRaisesRegex(MaintenanceError, 'No supported source change'):
            await self.engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})
        self.assertEqual(self.engine.maintenance.candidates(), [])

    async def test_local_test_and_activation_still_require_explicit_approval(self):
        report = await self.analyze()
        candidate = await self.engine.execute('stage_repository_upgrade', 'general', {'analysis_id': report['id'], 'opportunity': 0})
        for action in ('test_repair_candidate','activate_repair_candidate'):
            with self.subTest(action=action), self.assertRaisesRegex(MaintenanceError, 'pprov'):
                await self.engine.execute(action, 'general', {'id': candidate['id'], 'approved': False})
        self.assertEqual(self.target.read_text(), 'def calculate(x):\n    return x\n')

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
