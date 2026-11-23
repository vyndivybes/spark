import asyncio
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_browser_voice import parse_browser_voice,perform_browser_voice

class ParserTests(unittest.TestCase):
    def test_navigate_and_inspect(self):
        self.assertEqual(parse_browser_voice("Spark, browser open github.com"),
                         {"action":"navigate","text":"https://github.com"})
        self.assertEqual(parse_browser_voice("browser inspect this page"),{"action":"inspect"})
        self.assertEqual(parse_browser_voice("browser go back"),{"action":"back"})
    def test_malicious_and_unscoped_prompts_rejected(self):
        for text in ("open github.com","browser send message to everyone",
                     "browser open localhost:8000","browser open http://127.0.0.1:8080",
                     "browser open file:///etc/passwd","browser click purchase",
                     "browser open 192.168.1.1","browser open http://[::1]:9090"):
            with self.subTest(text=text):self.assertIsNone(parse_browser_voice(text))
class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_queues_to_current_authenticated_session_only(self):
        class Fake:
            def __init__(self,allow=True):
                self.allow=allow
                self.sessions={"owner":{"id":"view","workspace_token":"secret","task":type('Task',(),{'done':lambda _:False})()}}
                self.sent=[]
            def allowed(self,sid):return self.allow
            def _authorized(self,session):return session.get("workspace_token")=="secret"
            async def command(self,sid,data):self.sent.append((sid,data))
        fake=Fake()
        result=await perform_browser_voice(fake,"owner",{"action":"back"})
        self.assertTrue(result["ok"])
        self.assertEqual(fake.sent[0][1]["workspace_token"],"secret")
        self.assertEqual(fake.sent[0][1]["action"],"back")
        fake.allow=False
        result=await perform_browser_voice(fake,"owner",{"action":"inspect"})
        self.assertFalse(result["ok"])
        self.assertEqual(len(fake.sent),1)
    async def test_no_session_cannot_start_unauthorized_browser(self):
        class Fake:
            sessions={}
            def allowed(self,sid):return True
        result=await perform_browser_voice(Fake(),"owner",{"action":"back"})
        self.assertFalse(result["ok"])
if __name__=="__main__":unittest.main()
