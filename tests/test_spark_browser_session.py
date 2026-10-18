import asyncio
import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_browser_session import BrowserSessions, destination, register_browser_sessions


async def until(predicate, timeout=15):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


class BrowserSessionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        class Socket:
            async def emit(inner, event, data, room=None):
                self.events.append((event, data, room))
        self.page = AsyncMock()
        self.page.is_closed = lambda: False
        self.page.set_default_timeout = lambda value: None
        self.page.url = 'about:blank'
        self.page.screenshot.return_value = b'jpeg'
        self.browser = AsyncMock()
        self.browser.new_page.return_value = self.page
        self.driver = AsyncMock()
        self.launch = AsyncMock(return_value=(self.driver, self.browser))
        self.allowed = True
        self.sessions = BrowserSessions(Socket(), lambda sid: self.allowed, self.launch, interval=0.01)

    async def asyncTearDown(self):
        await self.sessions.close()

    async def start(self, sid='one', session_id='view'):
        await self.sessions.start(sid, {'session_id': session_id})
        await until(lambda: any(e[0] == 'web_browser_frame' and e[2] == sid for e in self.events))

    async def test_opens_without_audio_or_api_key_streams_and_cleans_up(self):
        await self.start()
        await until(lambda: len([e for e in self.events if e[0] == 'web_browser_frame']) >= 2)
        frames = [e for e in self.events if e[0] == 'web_browser_frame']
        self.assertEqual(frames[0][1]['mime_type'], 'image/jpeg')
        self.assertEqual(base64.b64decode(frames[0][1]['image']), b'jpeg')
        self.assertTrue(all(e[2] == 'one' for e in self.events))
        await self.sessions.stop('one')
        self.browser.close.assert_awaited_once()
        self.driver.stop.assert_awaited_once()

    async def test_duplicate_start_does_not_launch_twice_and_stale_stop_is_ignored(self):
        await self.start()
        await self.sessions.start('one', {'session_id': 'view'})
        await self.sessions.stop('one', {'session_id': 'old'})
        self.launch.assert_awaited_once()
        self.assertIn('one', self.sessions.sessions)

    async def test_clients_and_commands_are_isolated(self):
        await self.start()
        await self.sessions.command('other', {'session_id': 'view', 'text': 'https://example.com'})
        await self.sessions.command('one', {'session_id': 'old', 'text': 'https://example.com'})
        await asyncio.sleep(0.02)
        self.page.goto.assert_not_awaited()
        await self.sessions.command('one', {'session_id': 'view', 'text': 'https://example.com'})
        await until(lambda: self.page.goto.await_count == 1)
        self.assertEqual(self.page.goto.call_args.args[0], 'https://example.com')

    async def test_navigation_error_recovers_and_stream_continues(self):
        await self.start()
        self.page.goto.side_effect = TimeoutError('navigation timed out')
        await self.sessions.command('one', {'session_id': 'view', 'text': 'https://example.com'})
        await until(lambda: any('Action failed' in e[1].get('message', '') for e in self.events))
        await self.sessions.command('one', {'session_id': 'view', 'action': 'reload'})
        await until(lambda: self.page.reload.await_count == 1)
        self.assertFalse(self.sessions.sessions['one']['task'].done())

    async def test_permission_revocation_stops_existing_browser(self):
        await self.start()
        self.allowed = False
        await until(lambda: self.browser.close.await_count == 1)
        self.assertTrue(any(e[1].get('state') == 'error' for e in self.events))

    async def test_launch_failure_is_visible_and_retry_works(self):
        self.launch.side_effect = RuntimeError('Executable missing')
        await self.sessions.start('one', {'session_id': 'view'})
        await until(lambda: self.sessions.sessions['one']['task'].done())
        self.assertIn('python -m playwright install chromium', self.events[-1][1]['message'])
        self.launch.side_effect = None
        await self.start(session_id='retry')

    async def test_denied_session_never_launches(self):
        self.allowed = False
        await self.sessions.start('one', {'session_id': 'view'})
        self.launch.assert_not_awaited()
        self.assertEqual(self.events[-1][1]['state'], 'error')

    async def test_invalid_actions_do_not_reach_browser(self):
        for data in ({'action': 'navigate', 'text': 'file:///secret'},
                     {'action': 'click', 'x': float('nan'), 'y': 1},
                     {'action': 'type', 'text': 42}, {'action': 'key', 'key': 'arbitrary'}):
            with self.assertRaises(ValueError):
                await self.sessions._apply(self.page, data)
        self.page.goto.assert_not_awaited()
        self.page.mouse.click.assert_not_awaited()


class DestinationTests(unittest.TestCase):
    def test_urls_and_search(self):
        self.assertEqual(destination('example.com'), 'https://example.com')
        self.assertEqual(destination('http://localhost:8123/path'), 'http://localhost:8123/path')
        self.assertEqual(destination('spark browser'), 'https://www.google.com/search?q=spark+browser')
        for invalid in ('javascript:alert(1)', 'file:///secret', '', None, 'x' * 4097):
            with self.assertRaises(ValueError):
                destination(invalid)


@unittest.skipUnless(os.environ.get('SPARK_TEST_LOCAL_BROWSER') == '1', 'Opt-in real local Chromium and Socket.IO test')
class LocalBrowserIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_real_socket_session_navigation_frames_and_disconnect_cleanup(self):
        import socketio
        from aiohttp import web
        sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins=['http://127.0.0.1:5173'])
        app = web.Application()
        sio.attach(app)
        typed = []
        async def fixture(request):
            return web.Response(text='''<h1>SPARK fixture</h1>
                <input style="position:absolute;left:20px;top:100px;width:300px;height:40px"
                oninput="fetch('/typed?value='+encodeURIComponent(this.value))">''', content_type='text/html')
        async def record_typed(request):
            typed.append(request.query.get('value'))
            return web.Response(text='ok')
        app.router.add_get('/fixture', fixture)
        app.router.add_get('/typed', record_typed)
        sessions = register_browser_sessions(sio, lambda sid: sio.manager.is_connected(sid, '/'))
        async def disconnect(sid, reason=None):
            await sessions.stop(sid)
        sio.on('disconnect', disconnect)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        client = socketio.AsyncClient()
        frames, statuses = [], []
        client.on('web_browser_frame', lambda data: frames.append(data))
        client.on('web_browser_status', lambda data: statuses.append(data))
        try:
            await client.connect(f'http://127.0.0.1:{port}')
            await client.emit('start_web_browser', {'session_id': 'real'})
            await until(lambda: len(frames) >= 2 or any(s['state'] == 'error' for s in statuses), timeout=45)
            self.assertFalse(any(status['state'] == 'error' for status in statuses), statuses)
            self.assertTrue(base64.b64decode(frames[0]['image']).startswith(b'\xff\xd8'))
            await client.emit('web_browser_command', {'session_id': 'real', 'text': f'http://127.0.0.1:{port}/fixture'})
            await until(lambda: any('/fixture' in frame['url'] for frame in frames))
            self.assertFalse(any(status['state'] == 'error' for status in statuses), statuses)
            await client.disconnect()
            await until(lambda: not sessions.sessions)
            if os.environ.get('SPARK_TEST_BROWSER_UI') == '1':
                from playwright.async_api import async_playwright
                async with async_playwright() as driver:
                    browser = await driver.chromium.launch()
                    try:
                        page = await browser.new_page(viewport={'width': 650, 'height': 460})
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        await page.goto(f'http://127.0.0.1:5173/tests/browser-view.html?backend=http://127.0.0.1:{port}', timeout=60000)
                        image = page.get_by_alt_text('Browser View')
                        await image.wait_for(timeout=45000)
                        entry = page.get_by_role('textbox', name='URL, search, or text to type')
                        await entry.fill(f'http://127.0.0.1:{port}/fixture')
                        await page.get_by_role('button', name='Go', exact=True).click()
                        await page.get_by_title(f'http://127.0.0.1:{port}/fixture').wait_for()
                        box = await image.bounding_box()
                        scale = min(box['width'] / 1440, box['height'] / 900)
                        await image.click(position={
                            'x': (box['width'] - scale * 1440) / 2 + scale * 60,
                            'y': (box['height'] - scale * 900) / 2 + scale * 120,
                        })
                        await entry.fill('hello SPARK')
                        previous_frame = await image.get_attribute('src')
                        await page.get_by_role('button', name='Type', exact=True).click()
                        await until(lambda: 'hello SPARK' in typed)
                        await page.wait_for_function(
                            "previous => document.querySelector('img[alt=\"Browser View\"]').src !== previous",
                            arg=previous_frame,
                        )
                        if os.environ.get('SPARK_BROWSER_SCREENSHOT'):
                            await page.screenshot(path=os.environ['SPARK_BROWSER_SCREENSHOT'])
                        self.assertEqual(errors, [])
                        await page.get_by_role('button', name='Close browser').click()
                        await until(lambda: not sessions.sessions)
                    finally:
                        await browser.close()
        finally:
            if client.connected:
                await client.disconnect()
            await sessions.close()
            await runner.cleanup()
