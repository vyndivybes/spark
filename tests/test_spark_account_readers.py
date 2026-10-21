import asyncio
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_google_mcp import GoogleReader
from spark_slack_mcp import SlackReader
import httpx


class GoogleReaderTests(unittest.TestCase):
    def reader(self):
        return GoogleReader(Path(sys.executable).resolve(), 'selected@example.com')

    def test_wrong_account_cannot_return_files(self):
        with patch.object(GoogleReader, '_run', return_value={'emailAddress':'other@example.com'}) as run:
            result = self.reader().read('google-drive', 'list')
        self.assertEqual(result['state'], 'account_mismatch')
        self.assertEqual(run.call_count, 1)

    def test_selected_account_can_read_bounded_metadata(self):
        with patch('spark_google_mcp.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0, json.dumps({'emailAddress':'selected@example.com'}), ''),
            subprocess.CompletedProcess([], 0, json.dumps({'files':[{'name':'Fixture'}]}), ''),
        ]) as run:
            result = self.reader().read('google-drive', 'list')
        self.assertTrue(result['ok'])
        self.assertTrue(result['read_only'])
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertFalse(run.call_args.kwargs['shell'])
        params = json.loads(run.call_args.args[0][-1])
        self.assertEqual(params['pageSize'], 10)
        with self.assertRaises(ValueError):
            self.reader().read('google-drive', 'delete')

    def test_errors_never_include_raw_credential_output(self):
        with patch('spark_google_mcp.subprocess.run', return_value=subprocess.CompletedProcess(
                [], 1, 'private refresh token', 'private secret')):
            result = self.reader().read('gmail', 'profile')
        self.assertEqual(result['state'], 'authorization_required')
        self.assertNotIn('private', str(result))


class SlackReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_token_does_not_claim_account_access(self):
        result = await SlackReader('T123', token='').read('account')
        self.assertEqual(result['state'], 'authorization_required')

    async def test_workspace_mismatch_blocks_channel_reads(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'ok':True, 'team_id':'TOTHER'})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch('spark_slack_mcp.httpx.AsyncClient', return_value=client):
            result = await SlackReader('T123', token='fixture').read('channels')
        self.assertEqual(result['state'], 'account_mismatch')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, '/api/auth.test')

    async def test_verified_workspace_returns_identity_without_token(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={'ok':True, 'team_id':'T123', 'team':'fixture', 'user_id':'U1'})))
        with patch('spark_slack_mcp.httpx.AsyncClient', return_value=client):
            result = await SlackReader('T123', token='secret-token').read('account')
        self.assertTrue(result['ok'])
        self.assertNotIn('secret-token', str(result))
