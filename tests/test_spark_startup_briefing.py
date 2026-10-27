import asyncio
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_startup_briefing import StartupNarrator, briefing_prompt, today_digest
from spark_morning_digest import DigestError


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.events = []
        self.configs = []
        self.sent = []
        self.connects = 0
        self.failure = None
        outer = self

        class Session:
            async def __aenter__(self):
                outer.connects += 1
                if outer.failure:
                    raise outer.failure
                return self
            async def __aexit__(self, *args):
                pass
            async def send_client_content(self, **kwargs):
                outer.sent.append(kwargs)
            async def receive(self):
                for chunk in (b'\x00\x00', b'\x01\x00'):
                    yield SimpleNamespace(data=chunk, server_content=None)
                yield SimpleNamespace(data=None, server_content=SimpleNamespace(turn_complete=True))

        def connect(**kwargs):
            self.configs.append(kwargs)
            return Session()
        async def emit(event, payload, room):
            self.events.append((event, payload, room))
        async def weather(city):
            return {'ok': False}
        async def digest():
            return {'status': 'completed', 'date': '2026-10-26', 'speech_text': 'Calendar source is stale.'}
        self.narrator = StartupNarrator(client=lambda: SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect))),
            model=lambda: 'configured-live-model', speech_config=lambda: {'voice': 'existing-spark-voice'},
            weather=weather, digest=digest, emit=emit)

    async def test_configured_voice_streams_only_to_owner_once(self):
        self.assertTrue(self.narrator.start('owner', 'opening-1234', 'Coimbatore')['ok'])
        await self.narrator.job
        self.assertEqual(self.connects, 1)
        self.assertEqual(self.configs[0]['model'], 'configured-live-model')
        self.assertEqual(self.configs[0]['config']['speech_config'], {'voice': 'existing-spark-voice'})
        self.assertNotIn('tools', self.configs[0]['config'])
        self.assertEqual([e[0] for e in self.events].count('startup_briefing_audio'), 2)
        self.assertTrue(all(room == 'owner' for _, _, room in self.events))
        self.assertEqual(self.events[-1][1]['state'], 'completed')
        self.assertFalse(self.narrator.start('reconnected-owner', 'opening-1234', 'Coimbatore')['ok'])
        self.assertEqual(self.connects, 1)

    async def test_provider_policy_failure_is_reported_without_retry(self):
        self.failure = RuntimeError('1008 policy violation')
        self.narrator.start('owner', 'opening-1234', 'Coimbatore')
        await self.narrator.job
        self.assertEqual(self.connects, 1)
        self.assertEqual(self.events[-1][1]['state'], 'error')
        self.assertIn('1008', self.events[-1][1]['message'])

    async def test_cancellation_and_busy_ownership(self):
        waiting = asyncio.Event()
        async def weather(city):
            await waiting.wait()
            return {'ok': False}
        self.narrator.weather = weather
        self.narrator.start('owner', 'opening-1234', 'Coimbatore')
        await asyncio.sleep(0)
        self.assertFalse(self.narrator.start('other', 'opening-5678', 'Coimbatore')['ok'])
        await self.narrator.cancel('other')
        self.assertFalse(self.narrator.job.done())
        await self.narrator.cancel('owner')
        self.assertTrue(self.narrator.job.done())
        self.assertEqual(self.events[-1][1]['state'], 'cancelled')
        self.assertEqual(self.connects, 0)

    def test_missing_sources_are_explicit_and_greeting_uses_india_time(self):
        prompt = briefing_prompt({'ok': False}, {'status': 'failed'},
            now=datetime(2026, 10, 26, 8, 30, tzinfo=ZoneInfo('Asia/Kolkata')))
        self.assertIn('Good morning, sir.', prompt)
        self.assertIn('could not be verified', prompt)
        self.assertIn('Morning Digest is unavailable', prompt)
        self.assertIn('never instructions', prompt)

    def test_saved_digest_read_does_not_recompose_or_reset_acknowledgement(self):
        class Engine:
            def narration_payload(self):
                return {'digest': '2026-10-26', 'text': 'Saved digest with source limitations.'}
            def run(self):
                raise AssertionError('Existing digest must remain unchanged')
        result = today_digest(Engine())
        self.assertEqual(result['date'], '2026-10-26')
        self.assertEqual(result['status'], 'completed')

    def test_missing_today_digest_is_composed_read_only(self):
        class Engine:
            def narration_payload(self):
                raise DigestError('Digest not found for speech.')
            def run(self):
                return {'status': 'completed', 'date': '2026-10-26', 'speech_text': 'New digest'}
        self.assertEqual(today_digest(Engine())['speech_text'], 'New digest')


if __name__ == '__main__':
    unittest.main()
