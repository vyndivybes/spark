"""Behavioral tests for bounded, read-only Python feature evidence."""
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_feature_inventory import inventory_python_symbols


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')

    def test_only_public_api_names_and_metadata_are_exposed(self):
        self.put('core/skills.py', 'SECRET = "private source literal"\n'
                 'class SkillForge:\n    def synthesize(self, goal):\n        return SECRET\n'
                 'async def launch():\n    return SECRET\n')
        result = inventory_python_symbols(self.root)
        self.assertEqual(result['parsed_files'], 1)
        self.assertEqual(result['modules'][0]['path'], 'core/skills.py')
        self.assertEqual(result['modules'][0]['classes'][0]['name'], 'SkillForge')
        self.assertEqual(result['modules'][0]['classes'][0]['methods'], ['synthesize'])
        self.assertEqual(result['modules'][0]['functions'], ['launch'])
        self.assertNotIn('private source literal', str(result))
        self.assertNotIn('SECRET', str(result))
        self.assertEqual(result['proof'], 'static-symbols-only')

    def test_skips_hidden_dependency_and_overlimit_files(self):
        self.put('node_modules/ignored.py', 'def ignored(): pass\n')
        self.put('.git/ignored.py', 'def ignored(): pass\n')
        self.put('config/secrets.py', 'def secret(): pass\n')
        self.put('core/big.py', 'def big(): pass\n' + '#' * 500)
        self.put('core/ok.py', 'def useful(): pass\n')
        result = inventory_python_symbols(self.root, max_file_bytes=128)
        self.assertEqual([row['path'] for row in result['modules']], ['core/ok.py'])
        self.assertEqual(result['parsed_files'], 1)

    def test_handles_syntax_errors_without_claiming_feature_proof(self):
        self.put('ok.py', 'def run():\n    return 1\n')
        self.put('bad.py', 'def broken(:\n')
        result = inventory_python_symbols(self.root)
        self.assertEqual(result['parse_failures'], 1)
        self.assertEqual(result['parsed_files'], 1)
        self.assertFalse(result['runtime_verified'])

    def test_symlinks_never_followed(self):
        self.put('safe.py', 'def ok(): pass\n')
        try:
            (self.root / 'linked.py').symlink_to(self.root / 'safe.py')
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks cannot be created in this environment')
        self.assertEqual(inventory_python_symbols(self.root)['parsed_files'], 1)

    def test_respects_file_and_symbol_limits(self):
        self.put('a.py', '\n'.join(f'def f{i}(): pass' for i in range(40)))
        self.put('b.py', 'def another(): pass\n')
        result = inventory_python_symbols(self.root, max_files=1, max_symbols=5)
        self.assertEqual(result['parsed_files'], 1)
        self.assertEqual(result['symbol_count'], 5)
        self.assertTrue(result['truncated'])


class LicenseBoundaryTests(unittest.TestCase):
    def test_imported_restricted_or_unknown_sources_are_not_model_shareable(self):
        from spark_feature_inventory import model_shareable_reference
        self.assertFalse(model_shareable_reference({'imported': {}, 'license': {'permissive': False}}))
        self.assertFalse(model_shareable_reference({'imported': {}, 'license': {'class': 'unknown'}}))
        self.assertFalse(model_shareable_reference({'imported': {}}))
        self.assertTrue(model_shareable_reference({'imported': {}, 'license': {'permissive': True}}))
        self.assertTrue(model_shareable_reference({'repository': '/own/project', 'sources': []}))


if __name__ == '__main__':
    unittest.main()
