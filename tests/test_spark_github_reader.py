from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_github_mcp import RepositoryReader


class GithubReaderTests(unittest.TestCase):
    def test_only_host_selected_repository_and_read_commands_are_available(self):
        for repository in ('--help', 'owner/repo;delete', 'https://github.com/owner/repo', '../repo'):
            with self.assertRaises(ValueError):
                RepositoryReader(repository)
        reader = RepositoryReader('vyndivybes/spark')
        with self.assertRaises(ValueError):
            reader.read('delete')
        with patch('spark_github_mcp.shutil.which', return_value='gh.exe'):
            with patch('spark_github_mcp.subprocess.run', return_value=subprocess.CompletedProcess(
                    [], 0, '{"nameWithOwner":"vyndivybes/spark"}', '')) as run:
                result = reader.read('repository')
        self.assertTrue(result['ok'])
        self.assertTrue(result['read_only'])
        self.assertIn('vyndivybes/spark', run.call_args.args[0])
        self.assertFalse(run.call_args.kwargs['shell'])
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)

    def test_cli_error_output_is_not_returned(self):
        with patch('spark_github_mcp.shutil.which', return_value='gh.exe'):
            with patch('spark_github_mcp.subprocess.run', return_value=subprocess.CompletedProcess(
                    [], 1, 'sensitive provider body', 'private credential detail')):
                result = RepositoryReader('vyndivybes/spark').read('issues')
        self.assertFalse(result['ok'])
        self.assertNotIn('private credential', str(result))
        self.assertNotIn('sensitive provider', str(result))
