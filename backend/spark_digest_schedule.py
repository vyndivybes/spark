"""Durable daily IST notification job, shared by scheduled and manual launches."""
import asyncio
from datetime import datetime

from spark_morning_digest import IST, DigestError, ist_date


class DigestSchedule:
    def __init__(self, engine):
        self.engine = engine

    async def run_due(self, refresh, notify, *, now=None):
        now = self.engine.clock() if now is None else now
        schedule = self.engine.scheduled_time()
        if not schedule:
            return {'state': 'not_configured'}
        instant = datetime.fromtimestamp(now, IST)
        try:
            hour, minute = map(int, schedule.split(':'))
        except ValueError:
            return {'state': 'failed', 'phase': 'schedule', 'error': 'Invalid schedule format'}
        if (instant.hour, instant.minute) < (hour, minute):
            return {'state': 'waiting', 'schedule_ist': schedule}
        date = ist_date(now)
        with self.engine._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM deliveries WHERE date=?', (date,)).fetchone()
            if row and row['state'] == 'shown':
                return {'date': date, 'state': 'already_shown'}
            if row and ((row['lease_until'] or 0) > now or (row['next_retry'] or 0) > now):
                return {'date': date, 'state': 'waiting'}
            db.execute('INSERT OR REPLACE INTO deliveries VALUES(?,?,?,NULL,NULL,?,NULL)',
                       (date, 'running', now, now + 300))
        phase = 'refresh'
        receipt = None
        try:
            await refresh()
            phase = 'compose'
            digest = await asyncio.to_thread(self.engine.run, now=now)
            if digest.get('status') != 'completed':
                raise DigestError('Digest did not complete.')
            sources = digest.get('sources') or {}
            partial = any(value.get('state') != 'current' or value.get('stale')
                          for value in sources.values() if isinstance(value, dict))
            phase = 'notify'
            receipt = await notify({'date': date, 'partial': partial})
            if not isinstance(receipt, dict) or receipt.get('ok') is not True or receipt.get('state') != 'shown':
                raise DigestError('Desktop did not confirm notification submission.')
            with self.engine._db() as db:
                db.execute('UPDATE deliveries SET state=?,shown=?,lease_until=NULL,error=NULL WHERE date=?',
                           ('shown', self.engine.clock(), date))
            return {'date': date, 'state': 'shown', 'partial': partial,
                    'sources': {name: value.get('state') for name, value in sources.items()
                                if isinstance(value, dict)}, 'task_count': len(digest.get('tasks') or [])}
        except Exception as error:
            with self.engine._db() as db:
                db.execute('UPDATE deliveries SET state=?,next_retry=?,lease_until=NULL,error=? WHERE date=?',
                           ('failed', now + 60, type(error).__name__, date))
            return {'date': date, 'state': 'failed', 'phase': phase,
                    'error_type': type(error).__name__,
                    'notification_state': receipt.get('state') if isinstance(receipt, dict) else None}
