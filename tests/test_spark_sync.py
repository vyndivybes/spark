import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_sync import IntegrationSync


class Hub:
    def __init__(self):
        self.calls=[]
        self.value={'ok':True,'data':{'files':[{'id':'one','name':'engineering'}]}}
        self.fail=False
    def list(self):
        return [{'name':'google-drive','configured':True,'read_tools':['google_list_items','provider_delete']},
                {'name':'uninstalled','configured':False},
                {'name':'graphiti','configured':True,'read_tools':['graph_status','refresh_project_graph']}]
    async def execute(self,service,action,args):
        self.calls.append((service,action,args))
        if self.fail: raise RuntimeError('private credential detail')
        return {'content':[{'type':'text','text':json.dumps(self.value)}]}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.now=1000;self.hub=Hub()
        self.sync=IntegrationSync(self.temp.name,self.hub,clock=lambda:self.now)
        self.sync.configure(True,300)
    def tearDown(self):self.temp.cleanup()
    def cycle(self):return asyncio.run(self.sync.cycle())

    def test_only_fixed_read_tools_run_and_unchanged_snapshots_do_not_gain_versions(self):
        self.cycle();self.assertEqual(len(self.hub.calls),2)
        self.assertEqual({x[2]['name'] for x in self.hub.calls},{'google_list_items','graph_status'})
        self.cycle();self.assertEqual(len(self.hub.calls),2)
        self.now+=301;self.cycle()
        self.assertEqual(self.sync.status()['sources'][0]['version'],1)
        self.hub.value['data']['files'][0]['name']='new engineering'
        self.now+=301;self.cycle()
        self.assertEqual(self.sync.status()['sources'][0]['version'],2)

    def test_failures_keep_last_good_snapshot_and_back_off_without_error_leaks(self):
        self.cycle();self.hub.fail=True;self.now+=301;self.cycle()
        data=self.sync.cached('google-drive/google_list_items')
        self.assertEqual(data['data']['data']['files'][0]['id'],'one')
        self.assertEqual(data['state'],'failed')
        self.assertNotIn('credential',json.dumps(self.sync.status()))
        count=len(self.hub.calls);self.now+=100;self.cycle();self.assertEqual(len(self.hub.calls),count)
        self.now+=201;self.cycle()
        row=self.sync.status()['sources'][0];self.assertGreaterEqual(row['next_due']-self.now,600)

    def test_pause_persists_search_is_local_and_credentials_are_not_cached(self):
        self.hub.value['access_token']='do-not-store'
        self.cycle()
        self.assertEqual(len(self.sync.search('engineering')['results']),2)
        self.assertNotIn('do-not-store',json.dumps(self.sync.cached('google-drive/google_list_items')))
        self.sync.configure(False,900)
        other=IntegrationSync(self.temp.name,self.hub)
        self.assertEqual(other.settings(),{'enabled':False,'interval_seconds':900})
        self.now+=999;self.cycle();self.assertEqual(len(self.hub.calls),2)
        with self.assertRaises(ValueError):self.sync.cached('not-connected/arbitrary')

    def test_failed_payload_and_oversize_are_not_successful_snapshots(self):
        self.hub.value={'ok':False};self.cycle()
        self.assertIsNone(self.sync.cached('google-drive/google_list_items')['data'])
        self.hub.value={'ok':True,'data':'x'*1_000_001};self.now+=301;self.cycle()
        self.assertIsNone(self.sync.cached('google-drive/google_list_items')['data'])

    def test_scheduler_starts_pulls_then_stops_cleanly_and_authorization_is_enforced(self):
        async def run():
            await self.sync.start()
            for _ in range(30):
                if len(self.hub.calls)>=2:break
                await asyncio.sleep(.01)
            self.assertEqual(len(self.hub.calls),2)
            # Advancing the host clock and waking the scheduler must pull again
            # without a manual cycle or refresh request.
            while self.sync.lock.locked(): await asyncio.sleep(.01)
            self.now+=301;self.sync.wake.set()
            for _ in range(30):
                if len(self.hub.calls)>=4:break
                await asyncio.sleep(.01)
            self.assertEqual(len(self.hub.calls),4)
            await self.sync.close()
            self.assertTrue(self.sync.runner.done())
            self.sync.closed=False;self.sync.authorized=lambda:False;self.now+=999
            await self.sync.cycle();self.assertEqual(len(self.hub.calls),4)
        asyncio.run(run())

    def test_local_notes_participate_without_external_tools(self):
        self.sync.local=lambda:{'ok':True,'notes':[{'text':'local note'}]}
        self.cycle()
        self.assertEqual(self.sync.search('local note')['results'][0]['service'],'obsidian')
