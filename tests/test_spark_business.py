import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_business import BusinessClient
from spark_integrations import Integrations
from spark_connectivity import Connectivity


class BusinessTests(unittest.TestCase):
    def test_builtin_reads_are_available_without_extra_registry_slots_and_audited(self):
        async def run():
            hub=Integrations(config={})
            calls=[]
            async def read(portal):
                calls.append(portal)
                return {'ok':True,'readOnly':True,'sourceKind':'published-engineering-library','data':{}}
            hub.business=SimpleNamespace(configured=lambda:True,read=read)
            self.assertTrue(any(v['name']=='vedm' and v['configured'] for v in hub.list()))
            tools=await hub.execute('vedm','mcp_discover',{})
            self.assertEqual(tools[0]['name'],'read_vedm_library')
            with self.assertRaises(ValueError):
                await hub.execute('vedm','mcp_call',{'name':'read_vedm_library','arguments':{'url':'https://example.com'}})
            result=await hub.execute('vedm','mcp_call',{'name':'read_vedm_library','arguments':{}})
            self.assertTrue(json.loads(result['content'][0]['text'])['ok'])
            self.assertEqual(calls,['vedm'])
            self.assertTrue(hub.history()[0]['ok'])
        asyncio.run(run())

    def test_failed_actual_read_is_not_promoted_by_successful_discovery(self):
        async def run():
            hub=Integrations(config={})
            async def read(portal):return {'ok':False,'code':'SIGN_IN_REQUIRED'}
            hub.business=SimpleNamespace(configured=lambda:True,read=read)
            report=await Connectivity(integrations=hub,env={}).report(deep=True)
            for entry in report['entries']:
                if entry['name'] in ('VYNDI OS','VEDM'):
                    self.assertEqual(entry['state'],'failed verification')
        asyncio.run(run())

    def test_unconfigured_client_does_not_make_a_network_request(self):
        client=BusinessClient(enabled=lambda:True,endpoint='',token='')
        self.assertFalse(asyncio.run(client.read('vedm'))['ok'])
