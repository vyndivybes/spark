import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from spark_google_mcp import GoogleReader
from spark_sync import IntegrationSync
from spark_morning_digest import DigestEngine, IST
from spark_digest_schedule import DigestSchedule
from spark_digest_google import ScheduledGoogleReads


class GoogleTasksTests(unittest.TestCase):
    def reader(self, wrong_account=False):
        reader = GoogleReader.__new__(GoogleReader)
        reader.account = 'owner@example.com'
        reader.config_dir = None
        self.calls = []

        def request(command, params):
            self.calls.append((command, params))
            if command[0] == 'gmail':
                return {'emailAddress': 'other@example.com' if wrong_account else reader.account}
            if command[1] == 'tasklists':
                return {'items': [{'id': 'tasks-list'}]}
            return {'items': [
                {'id': 'pending', 'title': 'Review proposal', 'due': '2026-10-24T00:00:00Z', 'status': 'needsAction'},
                {'id': 'done', 'title': 'Already done', 'status': 'completed'},
                {'id': 'deleted', 'deleted': True}, {'id': 'hidden', 'hidden': True}],
                'nextPageToken': 'more'}
        reader._run = request
        return reader

    def test_pending_tasks_are_bounded_read_only_and_account_verified(self):
        result = self.reader().read('google-tasks', 'briefing')
        self.assertTrue(result['ok'])
        self.assertTrue(result['read_only'])
        self.assertEqual([task['id'] for task in result['data']['tasks']], ['pending'])
        self.assertTrue(result['data']['possibly_truncated'])
        self.assertFalse(self.calls[-1][1]['showCompleted'])
        self.assertEqual(self.calls[-1][1]['maxResults'], 100)

    def test_account_mismatch_prevents_any_tasks_read(self):
        result = self.reader(wrong_account=True).read('google-tasks', 'briefing')
        self.assertEqual(result['state'], 'account_mismatch')
        self.assertEqual(len(self.calls), 1)

    def test_tasks_snapshot_reaches_digest_and_preserves_failure_state(self):
        class Integrations:
            def list(self):
                return [{'name': 'google-calendar', 'configured': True,
                         'read_tools': ['google_daily_briefing', 'google_tasks_briefing']}]
        with tempfile.TemporaryDirectory() as directory:
            sync = IntegrationSync(directory, Integrations())
            self.assertIn(('google-calendar', 'google_tasks_briefing', 'data'), sync.plan())
            body = {'ok': True, 'data': {'source': 'google-tasks',
                                       'tasks': [{'id': 't', 'title': 'Review proposal'}]}}
            with sync.db() as db:
                db.execute('INSERT INTO snapshots(id,service,tool,mode,body,last_success,state) VALUES(?,?,?,?,?,?,?)',
                           ('google-calendar/google_tasks_briefing', 'google-calendar', 'google_tasks_briefing',
                            'data', json.dumps(body), sync.clock(), 'current'))
            engine = DigestEngine(directory, sync)
            result = engine.run()
            self.assertEqual(result['tasks'][0]['title'], 'Review proposal')
            self.assertEqual(result['sources']['tasks']['state'], 'current')
            self.assertIn('Review proposal', result['speech_text'])
            with sync.db() as db:
                db.execute("UPDATE snapshots SET state='failed'")
            self.assertEqual(engine.run()['sources']['tasks']['state'], 'failed')


class DigestSchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now = datetime(2026, 10, 23, 7, 0, tzinfo=IST).timestamp()
        self.refreshes = 0
        self.notices = []
        class Sync:
            def briefing(inner):
                return {'sources': {'gmail': {'state': 'current', 'stale': False}},
                        'emails': [], 'events': [], 'documents': []}
        self.sync = Sync()
        self.engine = DigestEngine(self.directory.name, self.sync, clock=lambda: self.now)
        self.engine.configure(schedule_ist='07:00')

    async def refresh(self):
        self.refreshes += 1

    async def notify(self, payload):
        self.notices.append(payload)
        return {'ok': True, 'state': 'shown'}

    async def test_no_notification_before_7_then_one_per_day_after_restart(self):
        schedule = DigestSchedule(self.engine)
        self.assertEqual((await schedule.run_due(self.refresh, self.notify, now=self.now-1))['state'], 'waiting')
        self.assertEqual(self.refreshes, 0)
        self.assertEqual((await schedule.run_due(self.refresh, self.notify))['state'], 'shown')
        fresh_engine = DigestEngine(self.directory.name, self.sync, clock=lambda: self.now)
        self.assertEqual((await DigestSchedule(fresh_engine).run_due(self.refresh, self.notify))['state'], 'already_shown')
        self.assertEqual(len(self.notices), 1)
        self.now += 86400
        self.assertEqual((await schedule.run_due(self.refresh, self.notify))['state'], 'shown')
        self.assertEqual(len(self.notices), 2)

    async def test_unconfirmed_desktop_delivery_is_not_claimed_as_shown(self):
        async def failed(_):
            return {'ok': False, 'state': 'unsupported'}
        result = await DigestSchedule(self.engine).run_due(self.refresh, failed)
        self.assertEqual(result['state'], 'failed')
        self.assertIsNone(self.engine.status()['notification_delivery']['shown'])
        self.assertEqual((await DigestSchedule(self.engine).run_due(self.refresh, self.notify))['state'], 'waiting')
        self.now += 61
        self.assertEqual((await DigestSchedule(self.engine).run_due(self.refresh, self.notify))['state'], 'shown')

    async def test_concurrent_launches_submit_only_one_notice(self):
        results = await asyncio.gather(*[
            DigestSchedule(self.engine).run_due(self.refresh, self.notify) for _ in range(2)])
        self.assertEqual(len(self.notices), 1)
        self.assertEqual(sum(result['state'] == 'shown' for result in results), 1)

    async def test_failed_digest_is_not_announced_ready(self):
        self.sync.briefing = lambda: {'sources': {'gmail': {'state': 'failed'}}}
        self.assertEqual((await DigestSchedule(self.engine).run_due(self.refresh, self.notify))['state'], 'failed')
        self.assertEqual(self.notices, [])


class ScheduledGoogleReadsTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, tools=None, script=None):
        return ScheduledGoogleReads(config={'google-calendar': {
            'command': sys.executable,
            'args': [str(script or Path(__file__).resolve().parents[1] / 'backend/spark_google_mcp.py'),
                     '--cli', sys.executable, '--account', 'owner@example.com', '--service', 'google-calendar'],
            'read_tools': tools if tools is not None else ['google_tasks_briefing']}})

    async def test_reuses_account_bound_reader_for_approved_tasks(self):
        adapter = self.adapter()
        with patch.object(GoogleReader, 'read', return_value={'ok': True, 'data': {'tasks': []}}) as read:
            result = await adapter.execute('google-calendar', 'mcp_call',
                                           {'name': 'google_tasks_briefing', 'arguments': {}})
            self.assertTrue(result['structuredContent']['ok'])
            read.assert_called_once_with('google-tasks', 'briefing')

    async def test_missing_grant_custom_server_and_writes_never_read(self):
        for adapter, tool in ((self.adapter(tools=[]), 'google_tasks_briefing'),
                              (self.adapter(script=Path('unrelated.py')), 'google_tasks_briefing'),
                              (self.adapter(), 'google_save_calendar_event')):
            with patch.object(GoogleReader, 'read') as read:
                with self.assertRaises(ValueError):
                    await adapter.execute('google-calendar', 'mcp_call', {'name': tool, 'arguments': {}})
                read.assert_not_called()


@unittest.skipUnless(os.name == 'nt', 'Windows task registration integration')
class DigestConfigurationTests(unittest.TestCase):
    def setUp(self):
        from spark_workspace import SparkWorkspace
        from spark_workbench import Workbench
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workbench = Workbench(SparkWorkspace(Path(self.directory.name)))
        self.workbench.digest.configure(schedule_ist='07:00')
        with self.workbench.digest._db() as db:
            db.execute("INSERT INTO settings VALUES('windows_task','SPARK Morning Digest')")

    def test_invalid_news_setting_cannot_change_windows_schedule(self):
        with patch('subprocess.run') as run:
            with self.assertRaises(ValueError):
                self.workbench._digest_configure({'schedule_ist': '08:00', 'news_enabled': 'yes', 'news_url': ''})
            run.assert_not_called()
        self.assertEqual(self.workbench.digest.scheduled_time(), '07:00')

    def test_failed_windows_update_preserves_saved_schedule(self):
        with patch('subprocess.run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(ValueError):
                self.workbench._digest_configure({'schedule_ist': '08:00', 'news_enabled': False, 'news_url': ''})
        self.assertEqual(self.workbench.digest.scheduled_time(), '07:00')


if __name__ == '__main__':
    unittest.main()
