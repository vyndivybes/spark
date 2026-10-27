import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_integrations import Integrations
from spark_connectivity import Connectivity


class IntegrationResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_failure_is_returned_and_audited_as_failure(self):
        for representation in ('structuredContent', 'content'):
            with self.subTest(representation=representation):
                hub = Integrations(config={'gmail': {'command': 'unused',
                    'read_tools': ['google_account_status']}})
                value = {'ok': False, 'state': 'authorization_required'}
                result = {representation: value if representation == 'structuredContent'
                          else [{'type': 'text', 'text': json.dumps(value)}], 'isError': False}
                hub.clients['gmail'] = AsyncMock()
                hub.clients['gmail'].request.return_value = result
                response = await hub.execute('gmail', 'mcp_call',
                    {'name': 'google_account_status', 'arguments': {}})
                self.assertTrue(response['isError'])
                self.assertFalse(hub.history()[0]['ok'])

    async def test_plain_text_graph_answer_remains_successful(self):
        hub = Integrations(config={'graphify': {'command': 'unused', 'read_tools': ['query_graph']}})
        hub.clients['graphify'] = AsyncMock()
        hub.clients['graphify'].request.return_value = {'content': [{'type': 'text', 'text': '3 graph nodes'}]}
        result = await hub.execute('graphify', 'mcp_call', {'name': 'query_graph', 'arguments': {}})
        self.assertFalse(result.get('isError', False))
        self.assertTrue(hub.history()[0]['ok'])

    async def test_google_discovery_does_not_hide_expired_login(self):
        hub = Integrations(config={'gmail': {'command': 'unused', 'read_tools': ['google_account_status']}})
        hub.execute = AsyncMock(side_effect=[
            [{'name': 'google_account_status'}],
            {'content': [{'type': 'text', 'text': json.dumps({'ok': False, 'state': 'authorization_required'})}]},
        ])
        entry = {'server': 'gmail', 'evidence': 'Configured.'}
        await Connectivity(integrations=hub)._probe(entry)
        self.assertEqual(entry['state'], 'failed verification')
        self.assertEqual(hub.execute.await_count, 2)

    async def test_google_verified_requires_successful_account_read(self):
        hub = Integrations(config={'gmail': {'command': 'unused', 'read_tools': ['google_account_status']}})
        hub.execute = AsyncMock(side_effect=[
            [{'name': 'google_account_status'}],
            {'structuredContent': {'ok': True, 'read_only': True}},
        ])
        entry = {'server': 'gmail', 'evidence': 'Configured.'}
        await Connectivity(integrations=hub)._probe(entry)
        self.assertEqual(entry['state'], 'verified operational')
        self.assertEqual(hub.execute.await_args.args[2]['arguments'], {})

    async def test_google_discovery_without_account_tool_stays_partial(self):
        hub = Integrations(config={'gmail': {'command': 'unused', 'read_tools': ['other_tool']}})
        hub.execute = AsyncMock(return_value=[{'name': 'other_tool'}])
        entry = {'server': 'gmail', 'evidence': 'Configured.'}
        await Connectivity(integrations=hub)._probe(entry)
        self.assertEqual(entry['state'], 'partially operational')
        self.assertFalse(entry['probe']['account_verified'])
        self.assertEqual(hub.execute.await_count, 1)

    async def test_google_empty_account_result_is_not_verified(self):
        hub = Integrations(config={'gmail': {'command': 'unused', 'read_tools': ['google_account_status']}})
        hub.execute = AsyncMock(side_effect=[[{'name': 'google_account_status'}], {'structuredContent': {}}])
        entry = {'server': 'gmail', 'evidence': 'Configured.'}
        await Connectivity(integrations=hub)._probe(entry)
        self.assertEqual(entry['state'], 'failed verification')
