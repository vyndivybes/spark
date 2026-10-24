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


class OfficialQuotaFallbackTests(unittest.TestCase):
    def _read(self, status, triage=None, operation='pending', isolated=True, quota=True):
        with tempfile.TemporaryDirectory() as directory:
            reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com', directory if isolated else None)
            error = 'serviceusage.services.use permission required' if quota else 'Workspace policy denied access'
            responses = [subprocess.CompletedProcess([], 1, json.dumps({'error': {'code': 403, 'message': error}}), '')]
            responses.append(subprocess.CompletedProcess([], 0, json.dumps(status), ''))
            responses.append(subprocess.CompletedProcess([], 0, json.dumps(triage) if triage is not None else '', 'No messages found'))
            with patch('spark_google_mcp.subprocess.run', side_effect=responses) as run:
                result = reader.read('gmail', operation)
            return result, run.call_args_list

    def test_quota_failure_reads_official_mail_after_live_identity_check(self):
        result, calls = self._read({'user': 'work@example.com', 'token_valid': True},
                                  {'messages': [{'id': 'abc123', 'from': 'sender@example.com', 'subject': 'Review', 'date': 'today'}]})
        self.assertTrue(result['ok'])
        self.assertTrue(result['read_only'])
        self.assertEqual(result['data']['messages'][0]['subject'], 'Review')
        self.assertEqual(calls[1].args[0][1:], ['auth', 'status'])
        self.assertIn('+triage', calls[2].args[0])
        self.assertIn('5', calls[2].args[0])

    def test_wrong_or_unverified_identity_never_reads_mail(self):
        for status in ({'user': 'personal@example.com', 'token_valid': True},
                       {'user': 'work@example.com', 'token_valid': False},
                       {'token_valid': True}):
            with self.subTest(status=status):
                result, calls = self._read(status)
                self.assertFalse(result['ok'])
                self.assertEqual(len(calls), 2)

    def test_empty_mailbox_is_valid_only_after_verified_identity(self):
        result, calls = self._read({'user': 'work@example.com', 'token_valid': True})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['shown'], 0)
        self.assertEqual(result['data']['messages'], [])

    def test_general_permission_denial_and_personal_store_never_use_fallback(self):
        for options in ({'quota': False}, {'isolated': False}):
            result, calls = self._read({'user': 'work@example.com', 'token_valid': True}, **options)
            self.assertEqual(result['state'], 'permission_denied')
            self.assertEqual(len(calls), 1)

    def test_profile_reports_verified_account_without_inventing_mailbox_counts(self):
        result, calls = self._read({'user': 'work@example.com', 'token_valid': True}, operation='profile')
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['emailAddress'], 'work@example.com')
        self.assertNotIn('messagesTotal', result['data'])
        self.assertIn('--query=-in:spam -in:trash', calls[2].args[0])

    def test_helper_permission_denial_is_never_an_empty_mailbox_pass(self):
        result, calls = self._read({'user': 'work@example.com', 'token_valid': True},
                                  {'error': {'code': 403, 'message': 'Workspace policy denied access'}})
        self.assertFalse(result['ok'])
        self.assertEqual(result['state'], 'permission_denied')
        self.assertEqual(len(calls), 3)

    def test_malformed_helper_rows_are_not_reported_as_success(self):
        for rows in (None, ['bad'], [{'id': '../invalid'}]):
            with self.subTest(rows=rows):
                result, _ = self._read({'user': 'work@example.com', 'token_valid': True}, {'messages': rows})
                self.assertFalse(result['ok'])


class FullGmailSearchTests(unittest.TestCase):
    def test_search_reaches_whole_mailbox_without_unread_or_date_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com', directory)
            responses = [subprocess.CompletedProcess([], 0, '{"user":"work@example.com","token_valid":true}', ''),
                         subprocess.CompletedProcess([], 0, '{"messages":[{"id":"abc123","subject":"F1 score"}]}', '')]
            with patch('spark_google_mcp.subprocess.run', side_effect=responses) as run:
                result = reader.search('from:alan@example.com subject:"F1 score"', 1)
            self.assertTrue(result['ok'])
            self.assertTrue(result['data']['possibly_truncated'])
            query_args = [arg for arg in run.call_args.args[0] if arg.startswith('--query=')]
            self.assertEqual(query_args, ['--query=in:anywhere from:alan@example.com subject:"F1 score"'])
            self.assertTrue(run.call_args.kwargs['shell'] is False)

    def test_invalid_queries_and_limits_do_not_call_google(self):
        reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com')
        with patch('spark_google_mcp.subprocess.run') as run:
            for query, limit in [('', 20), ('x'*501, 20), ('hello\nworld', 20), ('Alan', True), ('Alan', 21), ('Alan', 0)]:
                self.assertFalse(reader.search(query, limit)['ok'])
            run.assert_not_called()

    def test_mismatched_account_cannot_search(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = GoogleReader(Path(sys.executable).resolve(), 'work@example.com', directory)
            with patch('spark_google_mcp.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"user":"personal@example.com","token_valid":true}', '')) as run:
                self.assertEqual(reader.search('Alan')['state'], 'account_mismatch')
            self.assertEqual(run.call_count, 1)


class OfficialVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_search_routes_query_and_official_account(self):
        response = {'content': [{'type': 'text', 'text': '{"ok":true,"data":{"messages":[]}}'}]}
        with patch.object(Integrations, 'execute', AsyncMock(return_value=response)) as execute:
            result = await execute_assistant_tool('search_email', {'query': 'Alan Christo', 'account': 'official'})
        self.assertTrue(result['ok'])
        execute.assert_awaited_once_with('gmail', 'mcp_call', {'name': 'google_search_email', 'arguments': {'query': 'Alan Christo', 'limit': 20, 'account': 'official'}})

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
