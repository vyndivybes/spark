import ast
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_pc_optimizer import PcOptimizer

class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.optimizer = PcOptimizer(self.root, sampler=lambda: {'cpu_percent': 10})
    def file(self, name, old=True):
        path = self.root / name
        path.write_bytes(b'1234')
        if old:
            age = time.time() - 8 * 86400
            os.utime(path, (age, age))
        return path
    def test_scan_is_read_only_and_scope_is_bounded(self):
        self.file('old.tmp'); self.file('new.tmp', False); self.file('important.txt')
        folder = self.root / 'folder.tmp'; folder.mkdir()
        (folder / 'nested.tmp').write_bytes(b'keep')
        result = self.optimizer.scan()
        self.assertEqual(result['files'], [{'name': 'old.tmp', 'bytes': 4}])
        self.assertTrue((self.root / 'old.tmp').exists())
    def test_confirmation_token_and_replay(self):
        path = self.file('old.tmp'); preview = self.optimizer.scan()
        for payload in ({}, {'confirmed': True, 'scan_id': 'wrong'}):
            with self.assertRaises(ValueError): self.optimizer.cleanup(payload)
        result = self.optimizer.cleanup({'confirmed': True, 'scan_id': preview['scan_id']})
        self.assertEqual(result, {'deleted': 1, 'skipped': 0, 'reclaimed_bytes': 4})
        self.assertFalse(path.exists())
        with self.assertRaises(ValueError):
            self.optimizer.cleanup({'confirmed': True, 'scan_id': preview['scan_id']})
    def test_changed_files_preserved(self):
        path = self.file('old.tmp'); preview = self.optimizer.scan(); path.write_bytes(b'changed')
        result = self.optimizer.cleanup({'confirmed': True, 'scan_id': preview['scan_id']})
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(path.read_bytes(), b'changed')
    def test_expired_plan(self):
        path = self.file('old.tmp'); preview = self.optimizer.scan()
        with patch('spark_pc_optimizer.time.monotonic', return_value=time.monotonic() + 601):
            with self.assertRaises(ValueError): self.optimizer.cleanup({'confirmed': True, 'scan_id': preview['scan_id']})
        self.assertTrue(path.exists())
    def test_replaced_preview(self):
        first = self.optimizer.scan(); self.optimizer.scan()
        with self.assertRaises(ValueError): self.optimizer.cleanup({'confirmed': True, 'scan_id': first['scan_id']})
    def test_endpoint_denies_unauthenticated_clients(self):
        source = Path('backend/server.py').read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'pc_optimizer_action')
        node.decorator_list = []
        events = []
        class Sio:
            async def emit(self, *args, **kwargs): events.append(args)
        namespace = {'sio': Sio(), 'workspace_access_allowed': lambda *a, **kw: False,
                     'os': os, 'SETTINGS': {}, 'authenticator': None, 'pc_optimizer': self.optimizer, 'asyncio': asyncio}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'handler', 'exec'), namespace)
        coroutine = namespace['pc_optimizer_action']('stranger', {'request_id': '1', 'action': 'cleanup', 'payload': {'confirmed': True}})
        with self.assertRaises(StopIteration): coroutine.send(None)
        self.assertFalse(events[0][1]['ok'])

if __name__ == '__main__': unittest.main()
