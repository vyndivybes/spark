import json
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from spark_google_mcp import GoogleReader
from spark_assistant_tools import execute_assistant_tool, ASSISTANT_INSTRUCTION, assistant_live_config
from spark_integrations import Integrations


class PendingEmailTests(unittest.TestCase):
    def reader(self):
        return GoogleReader(Path(sys.executable).resolve(), 'selected@example.com')

    def test_pending_reads_unread_inbox_subjects_without_changing_mail(self):
        reader = self.reader()
        with patch.object(reader, '_run', side_effect=[
            {'emailAddress': 'selected@example.com'},
            {'messages': [{'id': 'abc123'}], 'nextPageToken': 'more'},
            {'snippet': 'Please review the plan.', 'payload': {'headers': [
                {'name': 'Subject', 'value': 'Review requested'},
                {'name': 'From', 'value': 'Person <person@example.com>'},
                {'name': 'Date', 'value': 'Thu, 22 Oct 2026 10:00:00 +0530'}]}},
        ]) as run:
            result = reader.read('gmail', 'pending')
        self.assertTrue(result['ok'])
        self.assertTrue(result['read_only'])
        message = result['data']['messages'][0]
        self.assertEqual(message['subject'], 'Review requested')
        self.assertEqual(message['from'], 'Person <person@example.com>')
        self.assertEqual(run.call_args_list[1].args[1]['q'], 'in:inbox is:unread')
        self.assertEqual(run.call_args_list[2].args[1]['format'], 'metadata')
        self.assertTrue(result['data']['more_available'])
        self.assertFalse(any(c.args[0][-1] in ('modify', 'send', 'delete') for c in run.call_args_list))

    def test_empty_inbox_is_a_successful_empty_result(self):
        reader = self.reader()
        with patch.object(reader, '_run', side_effect=[{'emailAddress': 'selected@example.com'}, {}]):
            result = reader.read('gmail', 'pending')
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['messages'], [])

    def test_wrong_account_cannot_list_mail(self):
        reader = self.reader()
        with patch.object(reader, '_run', return_value={'emailAddress': 'other@example.com'}) as run:
            result = reader.read('gmail', 'pending')
        self.assertEqual(result['state'], 'account_mismatch')
        self.assertEqual(run.call_count, 1)

    def test_unverified_inventory_is_not_an_oauth_failure(self):
        self.assertIn('Never ask the user to authorize again based only on connection inventory', ASSISTANT_INSTRUCTION)
        self.assertIn('MUST call get_pending_email directly', ASSISTANT_INSTRUCTION)
        config = assistant_live_config({'system_instruction': ''}, 'cinematic')
        names = [tool['name'] for group in config['tools'] for tool in group['function_declarations']]
        self.assertIn('get_pending_email', names)


class PendingEmailVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_directly_reads_mail_instead_of_stopping_at_inventory(self):
        expected = {'ok': True, 'data': {'messages': [{'subject': 'Review requested'}]}}
        response = {'content': [{'type': 'text', 'text': json.dumps(expected)}]}
        with patch.object(Integrations, 'execute', AsyncMock(return_value=response)) as execute:
            result = await execute_assistant_tool('get_pending_email', {})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data'], expected['data'])
        execute.assert_awaited_once_with('gmail', 'mcp_call', {'name': 'google_pending_email', 'arguments': {}})

    async def test_pending_email_rejects_write_arguments(self):
        with patch.object(Integrations, 'execute', AsyncMock()) as execute:
            result = await execute_assistant_tool('get_pending_email', {'mark_read': True})
        self.assertFalse(result['ok'])
        execute.assert_not_awaited()
