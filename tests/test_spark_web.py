"""Public-web boundaries and provider tool integration, without live requests."""
import asyncio
import json
import socket
import unittest
from unittest.mock import AsyncMock, patch

from spark_web import (PageText, PublicResolver, WEB_NAMES, execute_web_tool,
                       public_url, web_live_config)
from spark_groq import GroqClient, GroqVoiceLoop


class WebTests(unittest.IsolatedAsyncioTestCase):
    def test_only_public_web_urls(self):
        for url in ('http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/',
                    'http://192.168.1.1/', 'http://localhost/', 'http://printer.local/',
                    'file:///secret', 'https://user:pass@example.com/', 'https://example.com:9000/',
                    'https://example.com/\nsecret'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_url(url)
        self.assertEqual(public_url('https://www.python.org/'), 'https://www.python.org/')

    async def test_dns_mixed_with_private_addresses_is_rejected(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        loop = asyncio.get_running_loop()
        with patch.object(loop, 'getaddrinfo', AsyncMock(return_value=rows)):
            with self.assertRaises(ValueError):
                await PublicResolver().resolve('example.com', 443)

    async def test_search_returns_actual_source_links_and_plain_snippets(self):
        rss = '<rss><channel><item><title>Python</title><link>https://www.python.org/</link><description>&lt;b&gt;Official&lt;/b&gt; docs</description></item></channel></rss>'
        with patch('spark_web.fetch_text', AsyncMock(return_value=('https://www.bing.com/', rss))):
            result = await execute_web_tool('web_search', {'query': 'Python'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['results'][0]['snippet'], 'Official docs')
        self.assertEqual(result['sources'][0]['url'], 'https://www.python.org/')

    async def test_read_strips_scripts_and_bounds_content(self):
        page = '<h1>Visible</h1><script>hidden()</script><style>hidden</style><p>' + 'x' * 15000 + '</p>'
        with patch('spark_web.fetch_text', AsyncMock(return_value=('https://example.com/', page))):
            result = await execute_web_tool('read_web_page', {'url': 'https://example.com/'})
        self.assertNotIn('hidden', result['text'])
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['text']), 14000)

    async def test_network_failure_is_not_reported_as_verified(self):
        with patch('spark_web.fetch_text', AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await execute_web_tool('web_search', {'query': 'news'})
        self.assertFalse(result['ok'])
        self.assertNotIn('sources', result)

    async def test_javascript_shell_keeps_metadata_and_uses_bounded_renderer(self):
        page = '<html><head><title>Igloo Inc.</title><meta name="description" content="Our mission is to create the largest onchain community."><script src="/app.js"></script></head><body></body></html>'
        rendered = {'ok': True, 'text': 'Igloo Inc.\nAbout us\nOur ecosystem', 'canvas_count': 1}
        with patch('spark_web.fetch_text', AsyncMock(return_value=('https://www.igloo.inc/', page))), \
                patch('spark_web_render.render_public_page', AsyncMock(return_value=rendered)) as render:
            result = await execute_web_tool('read_web_page', {'url': 'igloo.inc'})
        self.assertEqual(result['method'], 'rendered_browser')
        self.assertIn('onchain community', result['description'])
        self.assertIn('Our ecosystem', result['text'])
        self.assertEqual(result['rendering']['canvas_count'], 1)
        render.assert_awaited_once_with('https://www.igloo.inc/')

    async def test_title_only_page_is_not_a_successful_content_read(self):
        with patch('spark_web.fetch_text', AsyncMock(return_value=('https://example.com/', '<title>Title only</title>'))):
            result = await execute_web_tool('read_web_page', {'url': 'https://example.com/'})
        self.assertFalse(result['ok'])
        self.assertNotIn('sources', result)

    async def test_unavailable_renderer_reports_metadata_limits(self):
        page = '<title>Igloo</title><meta name="description" content="Public mission statement"><script src="app.js"></script>'
        with patch('spark_web.fetch_text', AsyncMock(return_value=('https://www.igloo.inc/', page))), \
                patch('spark_web_render.render_public_page', AsyncMock(return_value={'ok': False})):
            result = await execute_web_tool('read_web_page', {'url': 'https://www.igloo.inc/'})
        self.assertEqual(result['method'], 'metadata_only')
        self.assertIn('visual design were not verified', result['limitations'])
        self.assertIn('Public mission statement', result['text'])

    async def test_unrelated_search_feed_is_rejected_and_fallback_used(self):
        rss = '<rss><channel><item><title>Azure</title><link>https://azure.microsoft.com/</link><description>Free account</description></item></channel></rss>'
        fallback = '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.igloo.inc%2F">Igloo Inc.</a><a class="result__snippet">Onchain community</a>'
        with patch('spark_web.fetch_text', AsyncMock(side_effect=[('https://www.bing.com/', rss), ('https://html.duckduckgo.com/', fallback)])):
            result = await execute_web_tool('web_search', {'query': 'igloo.inc'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['provider'], 'DuckDuckGo HTML')
        self.assertEqual(result['sources'][0]['url'], 'https://www.igloo.inc/')
        self.assertNotIn('Azure', str(result))

    async def test_unrelated_results_from_both_sources_are_never_cited(self):
        rss = '<rss><channel><item><title>Azure</title><link>https://azure.microsoft.com/</link></item></channel></rss>'
        with patch('spark_web.fetch_text', AsyncMock(side_effect=[('https://www.bing.com/', rss), ('https://html.duckduckgo.com/', '<p>No results</p>')])):
            result = await execute_web_tool('web_search', {'query': 'igloo.inc'})
        self.assertFalse(result['ok'])
        self.assertEqual(result['results'], [])
        self.assertNotIn('sources', result)

    def test_gemini_profiles_get_web_tools_without_altering_original(self):
        config = {'system_instruction': 'No tools are provided in cinematic voice mode.'}
        for profile in ('cinematic', 'cinematic_tools', 'cinematic_search', 'full'):
            result = web_live_config(config, profile)
            self.assertEqual({tool['name'] for tool in result['tools'][0]['function_declarations']}, WEB_NAMES)
            self.assertIn('untrusted', result['system_instruction'])
        self.assertNotIn('tools', config)
        self.assertIs(web_live_config(config, 'voice'), config)

    async def test_groq_executes_search_then_returns_grounded_answer_and_cards(self):
        client = GroqClient(key='test')
        cards = []
        client.on_web_sources = cards.append
        answer = 'Python docs: https://www.python.org/'
        client._http = AsyncMock(side_effect=[
            {'choices': [{'message': {'content': None, 'tool_calls': [
                {'id': 'search-1', 'type': 'function', 'function': {
                    'name': 'web_search', 'arguments': '{"query":"Python docs"}'}}]}}]},
            {'choices': [{'message': {'content': answer}}]},
        ])
        output = {'ok': True, 'sources': [{'title': 'Python', 'url': 'https://www.python.org/'}]}
        with patch('spark_groq.execute_web_tool', AsyncMock(return_value=output)) as execute:
            self.assertEqual(await client.chat('Find the current Python docs', []), answer)
        execute.assert_awaited_once_with('web_search', {'query': 'Python docs'})
        self.assertEqual(cards, [{'sources': output['sources']}])
        body = client._http.call_args.kwargs['body']
        self.assertEqual(body['messages'][-1]['role'], 'tool')
        self.assertEqual(json.loads(body['messages'][-1]['content']), output)

    def test_voice_wires_source_cards_to_client(self):
        client = GroqClient(key='test')
        callback = lambda payload: None
        GroqVoiceLoop(api=client, on_web_sources=callback)
        self.assertIs(client.on_web_sources, callback)
