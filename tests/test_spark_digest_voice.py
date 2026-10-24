import sys
import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_digest_voice import narration_prompt, submit_digest_voice
from spark_productivity import WorkbenchError
from spark_workbench_voice import parse_workbench_command


class DigestVoiceTests(unittest.IsolatedAsyncioTestCase):
    def payload(self):
        return {'digest': '2026-10-24', 'text': 'One pending task. Review the proposal.'}

    async def test_saved_digest_is_submitted_to_owning_gemini_session(self):
        send = AsyncMock()
        loop = SimpleNamespace(owner_sid='owner', session=SimpleNamespace(send_client_content=send))
        with patch('subprocess.run') as windows_speech:
            result = await submit_digest_voice(loop, 'owner', self.payload())
            windows_speech.assert_not_called()
        self.assertEqual(result['state'], 'submitted')
        prompt = send.call_args.kwargs['turns']['parts'][0]['text']
        self.assertIn(self.payload()['text'], prompt)
        self.assertIn('Do not search the web', prompt)
        self.assertTrue(send.call_args.kwargs['turn_complete'])

    async def test_no_session_foreign_owner_or_non_gemini_never_falls_back_to_os_speech(self):
        for loop in (None, SimpleNamespace(owner_sid='other', session=AsyncMock()),
                     SimpleNamespace(owner_sid='owner', session=None),
                     SimpleNamespace(owner_sid='owner', session=AsyncMock(), provider='groq')):
            with patch('subprocess.run') as windows_speech:
                with self.assertRaises(WorkbenchError):
                    await submit_digest_voice(loop, 'owner', self.payload())
                windows_speech.assert_not_called()

    async def test_spoken_commands_request_saved_digest_without_running_or_searching(self):
        for phrase in ('play morning digest', 'read the morning digest',
                       'report my morning digest', 'speak the latest morning digest'):
            command = parse_workbench_command(phrase)
            self.assertEqual(command, {'action': 'digest_speech', 'payload': {'digest': ''}})

    async def test_missing_or_unbounded_saved_text_is_refused(self):
        for value in ({}, {'text': ''}, {'text': 'x' * 2401}):
            with self.assertRaises(WorkbenchError):
                narration_prompt(value)

    async def test_gemini_microphone_command_reads_saved_digest_through_owner_callback(self):
        source = Path(__file__).resolve().parents[1] / 'backend/spark.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.AsyncFunctionDef) and node.name == 'maybe_dispatch_graphify')
        namespace = {'asyncio': asyncio, 'parse_workbench_command': parse_workbench_command}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        read = AsyncMock(return_value=self.payload())
        loop = SimpleNamespace(_graphify_dispatched=False, _graphify_tool_used=False,
                               on_graphify_query=None, on_graphiti_query=None,
                               on_obsidian_search=None, on_executive_briefing=None,
                               on_workspace_action=read, _user_utterance='play morning digest')
        session = SimpleNamespace(send_client_content=AsyncMock())
        await namespace['maybe_dispatch_graphify'](loop, session)
        read.assert_awaited_once_with('morning_digest', {}, 'play morning digest')
        prompt = session.send_client_content.call_args.kwargs['turns']['parts'][0]['text']
        self.assertIn(self.payload()['text'], prompt)
        self.assertTrue(loop._graphify_dispatched)
