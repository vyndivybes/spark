import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_local_records import collect_records, default_root


class LocalRecordRootsTests(unittest.TestCase):
    def test_explicit_workspace_root_is_not_given_another_workspace_suffix(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SPARK_WORKSPACE_DATA_ROOT': folder}):
            self.assertEqual(default_root(), Path(folder))

    def test_default_windows_root_uses_local_app_data(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            with patch.dict(os.environ, {'SPARK_WORKSPACE_DATA_ROOT': ''}):
                self.assertEqual(default_root(), Path(folder)/'SPARK'/'workspace')

    def test_empty_real_workspace_does_not_substitute_sample_records(self):
        with tempfile.TemporaryDirectory() as folder:
            result = collect_records(folder)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['source'], 'Existing local SPARK records')


if __name__ == '__main__':
    unittest.main()
