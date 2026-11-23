import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"backend"))
from spark_browser_session import BrowserSessions

class TokenBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[]
        class Socket:
            async def emit(inner,name,payload,room=None):
                self.events.append((name,payload,room))
        self.page=AsyncMock()
        self.page.is_closed=lambda:False
        self.page.set_default_timeout=lambda _:None
        self.page.url='about:blank'
        self.page.screenshot.return_value=b'jpeg'
        browser=AsyncMock()
        browser.new_page.return_value=self.page
        self.launch=AsyncMock(return_value=(AsyncMock(),browser))
        self.sessions=BrowserSessions(Socket(),lambda sid:True,
            launcher=self.launch,interval=0.001,
            token_authorizer=lambda token:token=='A'*64)

    async def asyncTearDown(self):
        await self.sessions.close()

    async def test_start_rejects_missing_and_invalid_token_without_launch(self):
        await self.sessions.start('owner',{'session_id':'view'})
        await self.sessions.start('owner',{'session_id':'view','workspace_token':'bad'})
        self.launch.assert_not_awaited()
        self.assertNotIn('owner',self.sessions.sessions)

    async def test_valid_session_rejects_tokenless_commands_and_stop(self):
        await self.sessions.start('owner',{'session_id':'view','workspace_token':'A'*64})
        await self.sessions.command('owner',{'session_id':'view','action':'navigate','text':'https://example.com'})
        await asyncio.sleep(0.02)
        self.page.goto.assert_not_awaited()
        await self.sessions.stop('owner',{'session_id':'view'})
        self.assertIn('owner',self.sessions.sessions)
        await self.sessions.command('owner',{'session_id':'view','workspace_token':'A'*64,
                                              'action':'navigate','text':'https://example.com'})
        async with asyncio.timeout(3):
            while self.page.goto.await_count<1:await asyncio.sleep(0.01)
        self.assertEqual(self.page.goto.await_count,1)
        await self.sessions.stop('owner',{'session_id':'view','workspace_token':'A'*64})
        self.assertNotIn('owner',self.sessions.sessions)

    async def test_invalid_start_cannot_replace_existing_authorized_session(self):
        await self.sessions.start('owner',{'session_id':'real','workspace_token':'A'*64})
        await self.sessions.start('owner',{'session_id':'intruder','workspace_token':'bad'})
        self.assertEqual(self.sessions.sessions['owner']['id'],'real')

if __name__=='__main__':unittest.main()
