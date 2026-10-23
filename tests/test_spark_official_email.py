import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from spark_google_mcp import GoogleReader
from spark_assistant_tools import execute_assistant_tool
from spark_integrations import Integrations


class OfficialEmailTests(unittest.TestCase):
    def test_official_account_uses_its_own_store_without_inherited_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com', directory)
            with patch.dict(os.environ, {'GOOGLE_WORKSPACE_CLI_TOKEN': 'personal-secret', 'GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE': 'personal.json'}):
                with patch('spark_google_mcp.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"emailAddress":"work@example.com"}', '')) as run:
                    self.assertTrue(reader.read('gmail', 'profile')['ok'])
                environment = run.call_args.kwargs['env']
                self.assertEqual(environment['GOOGLE_WORKSPACE_CLI_CONFIG_DIR'], directory)
                self.assertNotIn('GOOGLE_WORKSPACE_CLI_TOKEN', environment)
                self.assertNotIn('GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE', environment)
            self.assertEqual(os.environ.get('GOOGLE_WORKSPACE_CLI_CONFIG_DIR'), None)

    def test_permission_denied_does_not_instruct_repeated_login(self):
        reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com')
        response = subprocess.CompletedProcess([], 1, json.dumps({'error': {'code': 403, 'message': 'private provider text'}}), '')
        with patch('spark_google_mcp.subprocess.run', return_value=response):
            result = reader.read('gmail', 'profile')
        self.assertEqual(result['state'], 'permission_denied')
        self.assertNotIn('private provider text', str(result))

    def test_secondary_login_cannot_read_personal_account_as_official(self):
        reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com')
        with patch.object(reader, '_run', return_value={'emailAddress': 'personal@example.com'}) as run:
            result = reader.read('gmail', 'pending')
        self.assertEqual(result['state'], 'account_mismatch')
        self.assertEqual(run.call_count, 1)


class OfficialVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_voice_read_selects_official_account(self):
        response = {'content': [{'type': 'text', 'text': '{"ok":true,"data":{"messages":[]}}'}]}
        with patch.object(Integrations, 'execute', AsyncMock(return_value=response)) as execute:
            result = await execute_assistant_tool('get_pending_email', {'account': 'official'})
        self.assertTrue(result['ok'])
        execute.assert_awaited_once_with('gmail', 'mcp_call', {'name': 'google_pending_email', 'arguments': {'account': 'official'}})

    async def test_unconfigured_arbitrary_account_label_cannot_be_selected(self):
        with patch.object(Integrations, 'execute', AsyncMock()) as execute:
            result = await execute_assistant_tool('get_pending_email', {'account': 'someone_else'})
        self.assertFalse(result['ok'])
        execute.assert_not_awaited()
