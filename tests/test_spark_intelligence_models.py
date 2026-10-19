import asyncio
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_intelligence.models import Models


class ModelsTests(unittest.IsolatedAsyncioTestCase):
    async def test_routing_uses_local_first_and_only_the_explicitly_selected_cloud(self):
        models=Models(config={'local':{'provider':'ollama','model':'existing','base_url':'http://127.0.0.1:11434','context':2048},'selected-cloud':{'provider':'groq','model':'configured','context':8192},'other-cloud':{'provider':'gemini','model':'configured','context':8192}})
        models.health={name:{'available':True,'state':'healthy'} for name in ('local','selected-cloud','other-cloud')}
        self.assertEqual(models.route('hello',allow_cloud=True,cloud_provider='selected-cloud')['id'],'local')
        models.health['local']['available']=False
        self.assertEqual(models.route('hello',allow_cloud=True,cloud_provider='selected-cloud')['id'],'selected-cloud')
        models.health['selected-cloud']['available']=False
        with self.assertRaises(ValueError):models.route('hello',allow_cloud=True,cloud_provider='selected-cloud')

    async def test_optional_local_engine_outage_fails_without_cloud_fallback(self):
        models=Models(config={'local':{'provider':'ollama','model':'existing','base_url':'http://127.0.0.1:1','context':2048}})
        status=await models.probe('local')
        self.assertFalse(status['available'])
        with self.assertRaises(ValueError):await models.generate('local','hello',allow_cloud=False)
        self.assertEqual(len(models.history),1)

    async def test_non_loopback_local_configuration_and_unknown_fields_are_rejected(self):
        for config in [{'local':{'provider':'ollama','model':'x','base_url':'http://example.com','context':2048}}, {'bad':{'provider':'shell','model':'x','command':'whoami'}}]:
            with self.assertRaises(ValueError):Models(config=config).catalog()

    async def test_actual_local_http_discovery_and_generation(self):
        requests=[]
        async def handle(reader,writer):
            header=await reader.readuntil(b'\r\n\r\n')
            requests.append(header.decode())
            size=next((int(line.split(b':',1)[1]) for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:')),0)
            if size:await reader.readexactly(size)
            body=b'{"models":[{"name":"existing"}]}' if b'/api/tags' in header else b'{"response":"Hello","prompt_eval_count":1,"eval_count":1}'
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
            await writer.drain();writer.close();await writer.wait_closed()
        server=await asyncio.start_server(handle,'127.0.0.1',0)
        port=server.sockets[0].getsockname()[1]
        try:
            models=Models(config={'local':{'provider':'ollama','model':'existing','base_url':f'http://127.0.0.1:{port}','context':2048}})
            self.assertTrue((await models.probe('local'))['available'])
            self.assertEqual((await models.generate('local','hello',allow_cloud=False))['answer'],'Hello')
            self.assertEqual(len(requests),2)
            server.close();await server.wait_closed()
            with self.assertRaises(ValueError):await models.generate('local','hello again',allow_cloud=False)
            self.assertFalse(models.catalog()[0]['available'])
        finally:server.close();await server.wait_closed()
