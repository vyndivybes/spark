"""Real Windows/Linux process restart acceptance, without hardware or providers."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ProcessRestartTests(unittest.TestCase):
    def phase(self,directory,phase,expected=0,without_packages=False):
        fixture=Path(__file__).parent/'fixtures'/'intelligence_process.py'
        result=subprocess.run([sys.executable]+(['-S'] if without_packages else [])+[str(fixture),directory,phase],capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,expected,result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def test_once_schedule_executes_once_across_three_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            self.phase(directory,'schedule')
            first=self.phase(directory,'tick')
            second=self.phase(directory,'tick')
            self.assertEqual(first['effects'],1)
            self.assertEqual(second['effects'],1)
            self.assertEqual(second['runs'],0)

    def test_checkpoint_resume_does_not_replay_the_first_step_in_a_new_process(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.phase(directory,'checkpoint')['effects'],1)
            resumed=self.phase(directory,'resume')
            self.assertEqual(resumed['cursor'],2)
            self.assertEqual(resumed['effects'],2)
            self.assertEqual(self.phase(directory,'resume')['effects'],2)

    def test_abrupt_exit_releases_worker_lease_and_requires_manual_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            self.phase(directory,'crash',expected=17)
            recovered=self.phase(directory,'inspect')
            self.assertEqual(recovered['state'],'interrupted')
            self.assertTrue(recovered['execution_denied'])

    def test_local_workbench_starts_with_all_site_packages_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            result=self.phase(directory,'without-packages',without_packages=True)
            self.assertEqual(result['state'],'completed')
            self.assertEqual(result['memory_mode'],'fts5')
            self.assertFalse(result['optional_modules_loaded'])
