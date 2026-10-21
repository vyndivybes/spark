import os
from pathlib import Path
import subprocess
import sys
import unittest


class HermesPipeTests(unittest.TestCase):
    def test_journey_finishes_while_parent_stdin_remains_open(self):
        backend = Path(__file__).resolve().parents[1] / 'backend'
        script = f'''
import sys
sys.path.insert(0, {str(backend)!r})
from spark_hermes_mcp import LearnedExperience, ALLOWED_COMMANDS
ALLOWED_COMMANDS['journey'] = ('-c', 'import sys; sys.stdin.read(); print("journey-complete")')
print(LearnedExperience(cli=sys.executable)._invoke('journey').strip(), flush=True)
'''
        process = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Leave the parent transport open: the child command must receive
            # its own EOF rather than consuming the parent's MCP transport.
            process.wait(timeout=12)
            output, error = process.communicate()
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(output.strip(), 'journey-complete')
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
