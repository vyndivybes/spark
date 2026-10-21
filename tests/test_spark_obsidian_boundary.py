import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_obsidian_integration import ObsidianIntegration


class VaultBoundaryTests(unittest.TestCase):
    def test_search_and_read_stay_inside_the_selected_vault(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / 'vault'
            sibling = Path(directory) / 'vault-private'
            vault.mkdir(); sibling.mkdir()
            (vault / 'VAOS.md').write_text('A linked VAOS portal note.', encoding='utf-8')
            (sibling / 'secret.md').write_text('Private outside note.', encoding='utf-8')
            with patch.dict(os.environ, {'SPARK_OBSIDIAN_VAULT':str(vault)}):
                integration = ObsidianIntegration()
            self.assertEqual(len(integration.search('VAOS')), 1)
            self.assertIn('linked VAOS', integration.read('VAOS'))
            with self.assertRaises(ValueError):
                integration.read('../vault-private/secret.md')
            with self.assertRaises(ValueError):
                integration.read(str(sibling / 'secret.md'))
