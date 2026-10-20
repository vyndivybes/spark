import asyncio
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_pc_access import PcAccess, pc_live_config
from spark_groq import GroqClient, GroqVoiceLoop
from spark_workspace_auth import workspace_client_allowed


class PcAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.enabled = True
        self.access = PcAccess(self.root / 'state', lambda: self.enabled)

    def tearDown(self):
        self.temp.cleanup()

    def test_absolute_paths_backup_unicode_copy_move_and_revoke(self):
        file = self.root / 'outside-project' / 'notes.txt'
        self.assertTrue(self.access.execute({'action': 'write', 'path': str(file), 'content': 'Original α'})['ok'])
        result = self.access.execute({'action': 'write', 'path': str(file), 'content': 'Changed β'})
        self.assertTrue(result['ok'], result)
        self.assertEqual(Path(result['backup']).read_text(encoding='utf-8'), 'Original α')
        self.assertEqual(self.access.execute({'action': 'read', 'path': str(file)})['content'], 'Changed β')
        copy = self.root / 'copied.txt'
        moved = self.root / 'moved.txt'
        self.assertTrue(self.access.execute({'action': 'copy', 'path': str(file), 'destination': str(copy)})['ok'])
        self.assertTrue(self.access.execute({'action': 'move', 'path': str(copy), 'destination': str(moved)})['ok'])
        self.assertFalse(copy.exists())
        self.assertEqual(moved.read_text(encoding='utf-8'), 'Changed β')
        self.enabled = False
        self.assertFalse(self.access.execute({'action': 'write', 'path': str(file), 'content': 'Denied'})['ok'])
        self.assertEqual(file.read_text(encoding='utf-8'), 'Changed β')
        audit = (self.root / 'state/actions.jsonl').read_text()
        self.assertNotIn('Changed β', audit)
        self.assertIn('"state": "finished"', audit)

    def test_listing_read_pagination_and_invalid_arguments(self):
        folder = self.root / 'listing'
        self.assertTrue(self.access.execute({'action': 'mkdir', 'path': str(folder)})['ok'])
        for i in range(205):
            (folder / f'{i:03}.txt').write_text('a' * 25000)
        page = self.access.execute({'action': 'list', 'path': str(folder)})
        self.assertEqual(len(page['entries']), 200)
        page = self.access.execute({'action': 'list', 'path': str(folder), 'offset': page['next_offset']})
        self.assertEqual(len(page['entries']), 5)
        page = self.access.execute({'action': 'read', 'path': str(folder / '000.txt')})
        self.assertEqual(len(page['content']), 24000)
        self.assertEqual(page['next_offset'], 24000)
        for invalid in (None, [], {'action': 'unknown', 'path': str(folder)}, {'action': 'read', 'path': str(folder), 'offset': -1}):
            self.assertFalse(self.access.execute(invalid)['ok'])

    def test_real_terminal_success_nonzero_and_timeout(self):
        command = "'pc-terminal-ok'" if os.name == 'nt' else 'printf pc-terminal-ok'
        result = self.access.execute({'action': 'run', 'command': command, 'cwd': str(self.root)})
        self.assertTrue(result['ok'], result)
        self.assertIn('pc-terminal-ok', result['stdout'])
        result = self.access.execute({'action': 'run', 'command': 'exit 7'})
        self.assertFalse(result['ok'])
        self.assertEqual(result['exit_code'], 7)
        command = 'Start-Sleep -Seconds 10' if os.name == 'nt' else 'sleep 10'
        result = self.access.execute({'action': 'run', 'command': command, 'timeout': 1})
        self.assertTrue(result['timed_out'])
        self.assertFalse(result['ok'])

    def test_real_program_launch_uses_literal_arguments(self):
        target = self.root / 'program-output.txt'
        source = "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('launched')"
        result = self.access.execute({'action': 'launch', 'path': sys.executable,
                                     'arguments': ['-c', source, str(target)]})
        self.assertTrue(result['ok'], result)
        import time
        deadline = time.monotonic() + 5
        while not target.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual(target.read_text(), 'launched')

    def test_live_config_is_opt_in_and_validates_with_installed_sdk(self):
        from google.genai import types
        base = {'response_modalities': ['AUDIO'], 'system_instruction': 'No tools are provided in cinematic voice mode.'}
        self.assertIs(pc_live_config(base, False), base)
        enabled = pc_live_config(base, True)
        self.assertNotIn('tools', base)
        self.assertEqual(enabled['tools'][0]['function_declarations'][0]['name'], 'pc_action')
        types.LiveConnectConfig.model_validate(enabled)
        full = types.LiveConnectConfig(response_modalities=['AUDIO'], tools=[{'function_declarations': [{'name': 'write_file'}, {'name': 'read_file'}]}])
        converted = pc_live_config(full, True)
        names = [f['name'] for t in converted['tools'] for f in t.get('function_declarations', [])]
        self.assertEqual(names, ['pc_action'])
        types.LiveConnectConfig.model_validate(converted)


class PcProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_groq_tool_roundtrip_really_writes_and_reads_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            access = PcAccess(root / 'state', lambda: True)
            target = root / 'real-result.txt'
            calls = []

            class Client(GroqClient):
                async def _http(self, url, **kwargs):
                    body = kwargs['body']
                    calls.append(body)
                    if len(calls) == 1:
                        return {'choices': [{'message': {'content': None, 'tool_calls': [{
                            'id': 'pc-1', 'type': 'function', 'function': {'name': 'pc_action', 'arguments': json.dumps({
                                'action': 'write', 'path': str(target), 'content': 'Provider-created file'})}}]}}]}
                    result = json.loads(body['messages'][-1]['content'])
                    self_test.assertTrue(result['ok'])
                    self_test.assertEqual(target.read_text(), 'Provider-created file')
                    return {'choices': [{'message': {'content': 'Saved the file.'}}]}

            self_test = self
            answer = await Client(key='test-not-a-real-key').chat_autonomous('Write a file', [], access, lambda: False)
            self.assertEqual(answer, 'Saved the file.')
            self.assertEqual(calls[-1]['messages'][-1]['tool_call_id'], 'pc-1')
            self.assertFalse(calls[-1]['parallel_tool_calls'])

    async def test_revocation_stops_provider_before_request(self):
        with tempfile.TemporaryDirectory() as folder:
            access = PcAccess(Path(folder), lambda: False)
            client = GroqClient(key='test-not-a-real-key')
            async def forbidden(*args, **kwargs):
                self.fail('No cloud call after revocation')
            client._http = forbidden
            answer = await client.chat_autonomous('Read something', [], access, lambda: False)
            self.assertIn('disabled', answer)

    async def test_voice_routes_program_request_through_autonomy(self):
        seen = []
        class Client:
            async def chat_autonomous(self, prompt, history, access, stopped):
                seen.append(prompt)
                return 'Program started.'
        loop = GroqVoiceLoop(api=Client())
        with tempfile.TemporaryDirectory() as folder:
            loop.pc_access = PcAccess(Path(folder), lambda: True)
            await loop.handle_text('open notepad')
        self.assertEqual(seen, ['open notepad'])


class PcSessionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def functions(self, names, scope):
        # Load the real handler definitions without starting hardware/services.
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'backend/server.py').read_text(encoding='utf-8'))
        selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        for node in selected:
            node.decorator_list = []
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'server.py', 'exec'), scope)

    async def test_session_requires_trusted_connected_owner_and_revokes(self):
        stopped = asyncio.Event()
        settings = {'pc_autonomy_enabled': True}
        loop = SimpleNamespace(owner_sid='owner', stop_event=stopped)
        sio = SimpleNamespace(get_environ=lambda sid: {'HTTP_ORIGIN': 'https://unrelated.example'},
                              manager=SimpleNamespace(is_connected=lambda sid, ns: True))
        scope = dict(PcAccess=PcAccess, _SPARK_WORKSPACE_ROOT=Path(tempfile.gettempdir()),
                     workspace_client_allowed=workspace_client_allowed, sio=sio, os=os,
                     SETTINGS=settings, audio_loop=loop, authenticator=None)
        self.functions({'session_pc_access'}, scope)
        access = scope['session_pc_access']('owner', {})
        self.assertFalse(access.enabled())
        sio.get_environ = lambda sid: {'HTTP_ORIGIN': 'http://localhost:5173'}
        access = scope['session_pc_access']('owner', {})
        self.assertTrue(access.enabled())
        settings['pc_autonomy_enabled'] = False
        self.assertFalse(access.enabled())
        settings['pc_autonomy_enabled'] = True
        loop.owner_sid = 'other'
        self.assertFalse(access.enabled())
        loop.owner_sid = 'owner'
        settings['face_auth_enabled'] = True
        self.assertFalse(access.enabled())
        scope['authenticator'] = SimpleNamespace(authenticated=True)
        self.assertTrue(access.enabled())
        stopped.set()
        self.assertFalse(access.enabled())

    async def test_untrusted_setting_changes_and_foreign_turns_are_denied(self):
        settings = {'pc_autonomy_enabled': False}
        sio = SimpleNamespace(get_environ=lambda sid: {'HTTP_ORIGIN': 'https://unrelated.example'}, emit=AsyncMock())
        saves = []
        scope = dict(SETTINGS=settings, workspace_client_allowed=workspace_client_allowed,
                     sio=sio, os=os, audio_loop=SimpleNamespace(owner_sid='owner'),
                     authenticator=None, save_settings=lambda: saves.append(True))
        self.functions({'update_settings', 'user_input', 'upload_memory'}, scope)
        await scope['update_settings']('visitor', {'pc_autonomy_enabled': True})
        self.assertFalse(settings['pc_autonomy_enabled'])
        self.assertFalse(saves)
        await scope['user_input']('visitor', {'text': 'run a command'})
        await scope['upload_memory']('visitor', {'memory': 'run a command'})
        sio.get_environ = lambda sid: {'HTTP_ORIGIN': 'http://localhost:5173'}
        await scope['update_settings']('owner', {'pc_autonomy_enabled': True})
        self.assertTrue(settings['pc_autonomy_enabled'])
        self.assertEqual(len(saves), 1)
