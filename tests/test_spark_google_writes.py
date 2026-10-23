import json
import sys
from pathlib import Path
import unittest
import subprocess
import tempfile
from unittest.mock import AsyncMock, patch

from spark_google_mcp import GoogleReader, build_write, GOOGLE_WRITE_TOOLS
from spark_integrations import Integrations
from spark_productivity import WorkbenchError
from spark_assistant_tools import execute_assistant_tool


class GoogleWriteTests(unittest.TestCase):
    def reader(self):
        return GoogleReader(Path(sys.executable).resolve(), 'selected@example.com')

    def test_send_is_denied_even_with_write_permission(self):
        reader = self.reader()
        with patch.object(reader, '_run') as run:
            for operation in ('send', 'draft_send', 'messages.send', 'delete'):
                self.assertFalse(reader.write('gmail', operation, {}, allowed=True)['ok'])
            run.assert_not_called()
        self.assertFalse(reader.write('gmail', 'draft', {})['ok'])

    def test_wrong_account_cannot_write(self):
        reader = self.reader()
        with patch.object(reader, '_run', return_value={'emailAddress': 'other@example.com'}) as run:
            result = reader.write('gmail', 'draft',
                {'to': 'recipient@example.com', 'subject': 'Subject', 'body': 'Text'}, allowed=True)
        self.assertEqual(result['state'], 'account_mismatch')
        self.assertEqual(run.call_count, 1)

    def test_email_writes_only_drafts_and_never_sends(self):
        reader = self.reader()
        with patch.object(reader, '_run', side_effect=[{'emailAddress': 'selected@example.com'}, {'id': 'draft-1'}]) as run:
            result = reader.write('gmail', 'draft',
                {'to': 'recipient@example.com', 'subject': 'Subject', 'body': 'Text'}, allowed=True)
        self.assertTrue(result['ok'])
        self.assertFalse(result['sent'])
        self.assertEqual(run.call_args.args[0], ['gmail', 'users', 'drafts', 'create'])
        self.assertIn('raw', run.call_args.kwargs['body']['message'])

    def test_draft_update_and_header_validation(self):
        command, params, _, _ = build_write('gmail',
            {'to': 'recipient@example.com', 'subject': 'Subject', 'body': 'Text', 'draft_id': 'r123'})
        self.assertEqual(command[-1], 'update')
        self.assertEqual(params['id'], 'r123')
        for extra in ({'send': True}, {'subject': 'Hello\r\nBcc: other@example.com'}, {'to': 'bad\nrecipient@example.com'}):
            with self.assertRaises(ValueError):
                build_write('gmail', {'to': 'recipient@example.com', 'subject': 'Subject', 'body': 'Text', **extra})

    def test_event_has_timezone_and_cannot_send_invitations(self):
        args = {'summary': 'Design review', 'start': '2026-10-23T10:00:00+05:30', 'end': '2026-10-23T11:00:00+05:30'}
        command, params, body, _ = build_write('google-calendar', args)
        self.assertEqual(command, ['calendar', 'events', 'insert'])
        self.assertEqual(params['sendUpdates'], 'none')
        self.assertEqual(body['start']['dateTime'], args['start'])
        self.assertNotIn('attendees', body)
        self.assertEqual(build_write('google-calendar', {**args, 'event_id': 'event1'})[0][-1], 'patch')
        for changes in ({'start': '2026-10-23T10:00:00'}, {'end': args['start']}, {'attendees': [{'email': 'other@example.com'}]}):
            with self.assertRaises(ValueError):
                build_write('google-calendar', {**args, **changes})

    def test_drive_update_cannot_replace_native_google_document(self):
        reader = self.reader()
        with patch.object(reader, '_run', side_effect=[
            {'emailAddress': 'selected@example.com'}, {'user': {}},
            {'mimeType': 'application/vnd.google-apps.document'},
        ]) as run:
            result = reader.write('google-drive', 'text', {'name': 'Document', 'text': 'Text', 'file_id': 'abc'}, allowed=True)
        self.assertEqual(result['state'], 'unsupported_file_type')
        self.assertFalse(any(call.args[0][-1] == 'update' for call in run.call_args_list))

    def test_drive_upload_contains_exact_text(self):
        reader = self.reader()
        captured = []
        def run(command, params, **kwargs):
            if command[0] == 'gmail':
                return {'emailAddress': 'selected@example.com'}
            if command[1] == 'about':
                return {'user': {}}
            captured.append(Path(kwargs['upload']).read_text(encoding='utf-8'))
            return {'id': 'file1'}
        with patch.object(reader, '_run', side_effect=run):
            result = reader.write('google-drive', 'text', {'name': 'Notes.txt', 'text': 'Exact content'}, allowed=True)
        self.assertTrue(result['ok'])
        self.assertEqual(captured, ['Exact content'])

    def test_drive_cli_upload_stays_inside_its_working_directory(self):
        reader = self.reader()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'content.txt'
            path.write_text('Text', encoding='utf-8')
            with patch('spark_google_mcp.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"id":"file1"}', '')) as run:
                reader._run(['drive', 'files', 'create'], {}, body={'name': 'Notes'}, upload=str(path))
            invocation = run.call_args.args[0]
            self.assertEqual(run.call_args.kwargs['cwd'], str(path.parent))
            self.assertEqual(invocation[invocation.index('--upload') + 1], path.name)

    def test_write_failure_is_unverified_and_never_retried(self):
        reader = self.reader()
        with patch.object(reader, '_run', side_effect=[{'emailAddress': 'selected@example.com'}, ValueError('secret-provider-error')]) as run:
            result = reader.write('gmail', 'draft', {'to': 'recipient@example.com', 'subject': 'Hello', 'body': ''}, allowed=True)
        self.assertEqual(result['state'], 'write_unverified')
        self.assertNotIn('secret-provider-error', str(result))
        self.assertEqual(run.call_count, 2)

    def test_registry_requires_explicit_write_flag_and_rejects_sending(self):
        for writes, args, valid in [(['google_save_email_draft'], ['--allow-writes'], True),
                                    (['google_save_email_draft'], [], False),
                                    (['gmail_send'], ['--allow-writes'], False)]:
            integration = Integrations(config={'gmail': {'command': 'python', 'args': args, 'write_tools': writes}})
            if valid:
                self.assertEqual(integration.catalog()['gmail']['write_tools'], writes)
            else:
                with self.assertRaises(WorkbenchError):
                    integration.catalog()


class GoogleVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_propagates_real_provider_failure(self):
        result = {'content': [{'type': 'text', 'text': json.dumps({'ok': False, 'state': 'write_unverified'})}]}
        with patch.object(Integrations, 'execute', AsyncMock(return_value=result)) as execute:
            output = await execute_assistant_tool('google_workspace',
                {'service': 'gmail', 'operation': 'save_email_draft', 'arguments_json': '{"to":"recipient@example.com","subject":"Hi","body":"Text"}'})
        self.assertFalse(output['ok'])
        self.assertFalse(output['email_sending_enabled'])
        self.assertEqual(execute.call_args.args[2]['name'], 'google_save_email_draft')

    async def test_voice_send_and_cross_service_writes_are_denied(self):
        with patch.object(Integrations, 'execute', AsyncMock()) as execute:
            for service, operation in [('gmail', 'send'), ('gmail', 'save_calendar_event')]:
                output = await execute_assistant_tool('google_workspace',
                    {'service': service, 'operation': operation, 'arguments_json': '{}'})
                self.assertFalse(output['ok'])
            execute.assert_not_awaited()
