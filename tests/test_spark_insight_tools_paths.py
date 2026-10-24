"""Portable behavioral acceptance for base-prefixed source reads."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_insight_tools import read_spark_source_file


class SourcePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for base in ('backend', 'src'):
            (self.root / base).mkdir()
            (self.root / base / 'example.py').write_text('value = 42\n')
        self.patcher = patch('spark_autonomous_engine.PROJECT_ROOT', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_relative_and_prefixed_paths_read_the_same_real_file(self):
        for base in ('backend', 'src'):
            for name in ('example.py', base + '/example.py', base + '\\example.py'):
                with self.subTest(base=base, name=name):
                    result = read_spark_source_file(name, base=base)
                    self.assertEqual(result['status'], 'ok')
                    self.assertEqual(result['content'], 'value = 42\n')
                    self.assertEqual(result['file_path'], name)

    def test_missing_file_stays_not_found(self):
        self.assertEqual(read_spark_source_file('backend/absent.py')['status'], 'not_found')

    def test_refused_paths_stay_unavailable(self):
        for name in ('../outside.py', 'backend/../.env', 'backend/../../outside.py', '.env'):
            with self.subTest(name=name):
                self.assertEqual(read_spark_source_file(name)['status'], 'unavailable')

    def test_existing_nested_backend_file_wins_over_retry(self):
        nested = self.root / 'backend' / 'backend'
        nested.mkdir()
        (nested / 'example.py').write_text('nested = True\n')
        self.assertEqual(read_spark_source_file('backend/example.py')['content'], 'nested = True\n')

    def test_refused_initial_read_is_never_retried(self):
        with patch('spark_insight_tools.read_source_file', return_value=(None, 'refused: source access')) as helper:
            self.assertEqual(read_spark_source_file('backend/example.py')['status'], 'unavailable')
            helper.assert_called_once_with('backend/example.py', base='backend')


if __name__ == '__main__':
    unittest.main()
