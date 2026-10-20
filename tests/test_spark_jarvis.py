import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_jarvis import JarvisClient,jarvis_question,jarvis_live_config
from spark_groq import GroqVoiceLoop


class JarvisTests(unittest.IsolatedAsyncioTestCase):
    def test_config_and_explicit_intent(self):
        from google.genai import types
        base={'response_modalities':['AUDIO']}
        self.assertIs(jarvis_live_config(base,False),base)
        config=jarvis_live_config(base,True)
        types.LiveConnectConfig.model_validate(config)
        self.assertEqual(config['tools'][0]['function_declarations'][0]['name'],'ask_vaos_jarvis')
        self.assertEqual(jarvis_question('Ask VAOS Jarvis, what is workforce status?'),'what is workforce status?')
        self.assertIsNone(jarvis_question('what is workforce status?'))
        for endpoint in ('https://example.com','http://127.0.0.1.evil:9000','http://127.0.0.1:9000/extra'):
            self.assertFalse(JarvisClient(lambda:True,endpoint,'a'*64).configured())

    async def test_real_loopback_transport_and_revocation(self):
        from aiohttp import web
        seen=[]
        async def ask(request):
            seen.append((request.headers.get('Authorization'),await request.json()))
            return web.json_response({'ok':True,'answer':'Source evidence HOLD.','readOnly':True,'advisoryOnly':True})
        app=web.Application();app.router.add_post('/ask',ask)
        runner=web.AppRunner(app);await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        enabled=True
        try:
            port=site._server.sockets[0].getsockname()[1]
            client=JarvisClient(lambda:enabled,f'http://127.0.0.1:{port}','a'*64)
            reply=await client.ask('What is workforce status?')
            self.assertTrue(reply['ok']);self.assertIn('HOLD',reply['answer'])
            self.assertEqual(seen[0][0],'Bearer '+'a'*64)
            enabled=False
            self.assertFalse((await client.ask('What is workforce status?'))['ok'])
            self.assertEqual(len(seen),1)
        finally:await runner.cleanup()

    async def test_groq_routes_explicit_jarvis_question_without_cloud_chat(self):
        seen=[];transcripts=[]
        class Jarvis:
            async def ask(self,question):
                seen.append(question)
                return {'ok':True,'answer':'Qualified evidence unavailable.'}
        loop=GroqVoiceLoop(api=object(),on_transcription=transcripts.append)
        loop.jarvis_access=Jarvis()
        await loop.handle_text('Ask Jarvis, what is workforce status?')
        self.assertEqual(seen,['what is workforce status?'])
        self.assertEqual(transcripts[-1]['text'],'Qualified evidence unavailable.')

    async def test_workbench_catalog_and_call_use_the_real_jarvis_adapter(self):
        from spark_integrations import Integrations
        from spark_productivity import WorkbenchError
        integration=Integrations(config={})
        class Jarvis:
            def configured(self):return True
            async def ask(self,question):return {'ok':True,'answer':question,'readOnly':True,'advisoryOnly':True}
        integration.jarvis=Jarvis()
        entries=[entry for entry in integration.list() if entry['name']=='vaos-jarvis']
        self.assertEqual(len(entries),1)
        self.assertTrue(entries[0]['configured'])
        tools=await integration.execute('vaos-jarvis','mcp_discover',{})
        self.assertEqual(tools[0]['name'],'ask_vaos_jarvis')
        result=await integration.execute('vaos-jarvis','mcp_call',{'name':'ask_vaos_jarvis','arguments':{'question':'What is workforce status?'}})
        self.assertFalse(result['isError'])
        with self.assertRaises(WorkbenchError):
            await integration.execute('vaos-jarvis','mcp_call',{'name':'execute_mission','arguments':{}})
