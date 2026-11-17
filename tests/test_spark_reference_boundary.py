"""Imported reference evidence stays structural when source sharing is restricted."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_maintenance import MaintenanceError
from spark_repo_upgrade import RepositoryUpgrades
from spark_repo_import import import_evidence


class ImportedReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_restricted_reference_never_reaches_model(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            class MaintenanceStub:
                backups = base / 'data' / 'maintenance'
                root = base / 'spark'
            model = AsyncMock()
            engine = RepositoryUpgrades(MaintenanceStub(), model)
            evidence = {
                'repository': 'example/restricted', 'imported': {'owner': 'example'},
                'license': {'class': 'unknown', 'permissive': False},
                'inventory': ['core/skill_forge.py'], 'limitations': [],
                'sources': [{'path': 'core/skill_forge.py', 'sha256': '0' * 64,
                             'content': 'copyrighted-source-would-leak'}],
            }
            with self.assertRaisesRegex(MaintenanceError, 'license|permission|sharing'):
                await engine.analyze('general', evidence, 'Compare skill forge')
            model.assert_not_awaited()

    async def test_staging_old_restricted_report_stays_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            class MaintenanceStub:
                backups = base / 'data' / 'maintenance'
                root = base / 'spark'
            model = AsyncMock()
            engine = RepositoryUpgrades(MaintenanceStub(), model)
            engine.read = lambda project, identity: {
                'imported': {'owner': 'example'},
                'license': {'class': 'unknown', 'permissive': False},
                'opportunities': [{'title': 'unauthorized'}],
            }
            with self.assertRaisesRegex(MaintenanceError, 'license|permission|sharing'):
                await engine.stage('general', '0' * 24, 0)
            model.assert_not_awaited()

    def test_imported_repository_returns_structural_inventory_without_source_body(self):
        def fake_clone(url, destination, *, timeout):
            (destination / 'core').mkdir(parents=True)
            (destination / 'LICENSE').write_text('PERSONAL-USE ONLY; NO REDISTRIBUTION', encoding='utf-8')
            (destination / 'core' / 'skill_forge.py').write_text(
                'SECRET = "do not expose this literal"\nclass SkillForge:\n'
                '    def synthesize(self):\n        return SECRET\n', encoding='utf-8')
        with patch('spark_repo_import._clone', side_effect=fake_clone):
            evidence = import_evidence('https://github.com/example/restricted',
                                       selected=['core/skill_forge.py'])
        self.assertFalse(evidence['license']['permissive'])
        api = evidence['python_api']
        self.assertEqual(api['proof'], 'static-symbols-only')
        self.assertEqual(api['modules'][0]['classes'][0]['name'], 'SkillForge')
        self.assertNotIn('do not expose this literal', str(api))


if __name__ == '__main__':
    unittest.main()
