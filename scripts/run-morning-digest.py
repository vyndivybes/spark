"""Run the configured daily digest without opening voice, camera or the cockpit."""
import asyncio
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--set-time', metavar='HH:MM', help='Save the daily IST schedule without running a digest.')
    parser.add_argument('--mark-installed', action='store_true', help='Record that the Windows scheduled task was installed.')
    parser.add_argument('--test-delivery', action='store_true', help='Test real source refresh and desktop delivery without consuming the daily notification receipt.')
    options = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'backend/.env', override=True)
    from spark_digest_google import ScheduledGoogleReads
    from spark_sync import IntegrationSync
    from spark_morning_digest import DigestEngine
    from spark_digest_schedule import DigestSchedule
    root = Path(os.environ.get('SPARK_WORKSPACE_DATA_ROOT') or
                Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.spark') / 'SPARK/workspace')
    integrations = ScheduledGoogleReads(audit_dir=root / 'integrations')
    sync = IntegrationSync(root, integrations)
    engine = DigestEngine(root, sync)
    if options.mark_installed:
        with engine._db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('windows_task','SPARK Morning Digest')")
        print(json.dumps({'windows_task': 'SPARK Morning Digest'}))
        return 0
    if options.set_time:
        current = engine.status()
        engine.configure(schedule_ist=options.set_time, news_enabled=current['news_enabled'], news_url=current['news_url'])
        print(json.dumps({'schedule_ist': engine.scheduled_time()}))
        return 0

    async def refresh():
        await sync.cycle(force=True, services={'gmail', 'google-drive', 'google-calendar'})

    async def notify(payload):
        executable = ROOT / 'node_modules/electron/dist/electron.exe'
        env = os.environ.copy()
        env.pop('ELECTRON_RUN_AS_NODE', None)
        process = await asyncio.create_subprocess_exec(
            str(executable), str(ROOT / 'electron/digest-notify.cjs'),
            payload['date'], 'partial' if payload['partial'] else 'complete',
            env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            # Cold Electron startup on a busy Windows desktop can exceed 30s.
            output, _ = await asyncio.wait_for(process.communicate(), timeout=90)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {'ok': False, 'state': 'timeout'}
        for line in output.decode('utf-8', 'replace').splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict) and 'ok' in value:
                    return value
            except ValueError:
                continue
        return {'ok': False, 'state': 'unconfirmed'}

    try:
        if options.test_delivery:
            await refresh()
            digest = await asyncio.to_thread(engine.run)
            sources = digest.get('sources') or {}
            partial = any(value.get('state') != 'current' or value.get('stale')
                          for value in sources.values() if isinstance(value, dict))
            receipt = await notify({'date': digest['date'], 'partial': partial}) if digest.get('status') == 'completed' else {'ok': False, 'state': 'digest_failed'}
            result = {'mode': 'delivery_test', 'date': digest['date'],
                      'state': receipt.get('state') if receipt.get('ok') is True else 'failed',
                      'notification_state': receipt.get('state'), 'partial': partial,
                      'sources': {name: value.get('state') for name, value in sources.items() if isinstance(value, dict)},
                      'task_count': len(digest.get('tasks') or [])}
        else:
            result = await DigestSchedule(engine).run_due(refresh, notify)
        target = root / ('morning-digest/last-delivery-test.json' if options.test_delivery else 'morning-digest/last-scheduled-run.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result))
        return 1 if result.get('state') == 'failed' else 0
    finally:
        await integrations.close()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
