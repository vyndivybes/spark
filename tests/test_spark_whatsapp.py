import unittest
from unittest.mock import patch
from types import SimpleNamespace

from aiohttp import web
from spark_whatsapp import whatsapp_status
from spark_assistant_tools import execute_assistant_tool, ASSISTANT_INSTRUCTION


class WhatsAppStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.payload = {'ok': True, 'state': 'connected', 'readOnly': True,
                        'sending_enabled': False, 'chat_reading_available': False,
                        'phone_identity_verified': False, 'messages': ['must never escape']}
        self.requests = []
        async def status(request):
            self.requests.append((request.headers.get('Authorization'), await request.json()))
            return web.json_response(self.payload)
        app = web.Application()
        app.router.add_post('/whatsapp-status', status)
        app.router.add_post('/whatsapp-read', status)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.bridge = SimpleNamespace(endpoint=f'http://127.0.0.1:{port}', token='x'*64, enabled=lambda: True)

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_connected_session_is_exposed_without_private_content(self):
        with patch('spark_whatsapp.JarvisClient', return_value=self.bridge):
            result = await execute_assistant_tool('get_whatsapp_status', {})
        self.assertEqual(result['state'], 'connected')
        self.assertNotIn('messages', result)
        self.assertFalse(result['sending_enabled'])
        self.assertEqual(self.requests, [('Bearer '+'x'*64, {})])

    async def test_missing_bridge_means_unknown_not_disconnected(self):
        self.bridge.enabled = lambda: False
        with patch('spark_whatsapp.JarvisClient', return_value=self.bridge):
            result = await whatsapp_status()
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(result['ok'])
        self.assertEqual(self.requests, [])

    async def test_invalid_status_cannot_authorize_sending(self):
        self.payload['sending_enabled'] = True
        with patch('spark_whatsapp.JarvisClient', return_value=self.bridge):
            result = await whatsapp_status()
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(result['sending_enabled'])

    async def test_status_rejects_chat_commands(self):
        result = await execute_assistant_tool('get_whatsapp_status', {'read_chat': 'someone'})
        self.assertFalse(result['ok'])
        self.assertEqual(self.requests, [])

    def test_voice_must_check_the_session_and_distinguish_chat_capabilities(self):
        self.assertIn('MUST call get_whatsapp_status', ASSISTANT_INSTRUCTION)
        self.assertIn('absence from that registry is not a disconnection', ASSISTANT_INSTRUCTION)

    async def test_preview_read_filters_unexpected_fields_and_never_enables_sending(self):
        self.payload.update(chats=[{'title': 'Project team', 'preview': 'Sam: Review at 10', 'unread': True, 'token': 'private'}])
        with patch('spark_whatsapp.JarvisClient', return_value=self.bridge):
            result = await execute_assistant_tool('read_whatsapp_chats', {'query': 'review', 'limit': 3, 'unread_only': True})
        self.assertTrue(result['ok'])
        self.assertEqual(result['chats'], [{'title': 'Project team', 'preview': 'Sam: Review at 10', 'unread': True}])
        self.assertNotIn('private', str(result))
        self.assertFalse(result['sending_enabled'])
        self.assertEqual(self.requests[0][1], {'query': 'review', 'limit': 3, 'unread_only': True})

    async def test_preview_read_requires_linking_when_session_is_not_connected(self):
        self.payload = {'ok': False, 'state': 'link_required', 'sending_enabled': False}
        with patch('spark_whatsapp.JarvisClient', return_value=self.bridge):
            result = await execute_assistant_tool('read_whatsapp_chats', {})
        self.assertFalse(result['ok'])
        self.assertEqual(result['state'], 'link_required')

    async def test_preview_read_rejects_send_commands_and_invalid_limits(self):
        with patch('spark_whatsapp.JarvisClient', return_value=self.bridge):
            for args in ({'command': 'send'}, {'limit': True}, {'limit': 100}, {'unread_only': 'yes'}):
                result = await execute_assistant_tool('read_whatsapp_chats', args)
                self.assertFalse(result['ok'])
        self.assertEqual(self.requests, [])

    def test_voice_attempts_preview_tool_instead_of_blanket_refusal(self):
        self.assertIn('MUST call read_whatsapp_chats before answering', ASSISTANT_INSTRUCTION)
