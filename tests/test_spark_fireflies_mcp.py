"""Fireflies read-only MCP registration and host-secret guard tests."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_integrations import Integrations
from spark_productivity import WorkbenchError

ENTRY = {'transport':'streamable-http','url':'https://api.fireflies.ai/mcp',
         'secret_name':'fireflies_api_key','read_tools':['get_user','get_transcripts','get_summary'],
         'write_tools':[]}

class CatalogTests(unittest.TestCase):
    def test_secret_reference_is_accepted_only_for_exact_official_fireflies_endpoint(self):
        self.assertEqual(Integrations(config={'fireflies': ENTRY}).catalog()['fireflies']['secret_name'],
                         'fireflies_api_key')
        for bad in (
            {**ENTRY,'url':'https://example.com/mcp'},
            {**ENTRY,'write_tools':['share_meeting']},
            {**ENTRY,'headers':{'Authorization':'Bearer plaintext'}},
            {**ENTRY,'secret_name':'arbitrary'},
            {**ENTRY,'read_tools':['share_meeting']},
        ):
            with self.subTest(bad=list(bad)):
                with self.assertRaises(WorkbenchError):
                    Integrations(config={'fireflies':bad}).catalog()

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_secret_does_not_start_network_client(self):
        with patch('spark_credential_store.CredentialStore') as store, patch('spark_integrations.ReaClient') as client:
            store.return_value.load.return_value=None
            integrator=Integrations(config={'fireflies':ENTRY})
            with self.assertRaises(WorkbenchError):
                await integrator.execute('fireflies','mcp_discover',{})
            client.assert_not_called()

    async def test_dpapi_secret_is_sent_only_as_transient_bearer_header(self):
        with patch('spark_credential_store.CredentialStore') as store, patch('spark_integrations.ReaClient') as client:
            store.return_value.load.return_value='FAKE-LOCAL-SECRET-12345'
            client.return_value.close=unittest.mock.AsyncMock()
            client.return_value.request=unittest.mock.AsyncMock(return_value=[
                {'name':'get_user','inputSchema':{'type':'object','properties':{}}}
            ])
            integrator=Integrations(config={'fireflies':ENTRY})
            result=await integrator.execute('fireflies','mcp_discover',{})
            self.assertEqual(result[0]['name'],'get_user')
            self.assertEqual(client.call_args.kwargs['headers']['Authorization'],'Bearer FAKE-LOCAL-SECRET-12345')
            self.assertNotIn('FAKE-LOCAL-SECRET-12345',json.dumps(integrator.list()))
            self.assertNotIn('FAKE-LOCAL-SECRET-12345',json.dumps(integrator.history()))
            await integrator.close()

    async def test_mutating_provider_tools_are_rejected(self):
        integration=Integrations(config={'fireflies':ENTRY})
        with self.assertRaises(WorkbenchError):
            await integration.execute('fireflies','mcp_call',
                                      {'name':'share_meeting','arguments':{}})
if __name__=='__main__': unittest.main()
