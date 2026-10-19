"""Durable, approval-bound execution of bounded local tool plans.

Running reservations survive crashes as interrupted jobs. They require explicit
resume because an external effect may have happened before its checkpoint.
"""
import asyncio
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


class PolicyError(ValueError):
    pass


class Runtime:
    ACTIONS = frozenset({'get_system_status', 'run_skill', 'search_documents', 'list_documents','mcp_read'})

    def __init__(self, data_dir, *, executor, clock=time.time,concurrency=1):
        if type(concurrency) is not int or concurrency not in (1,2):raise PolicyError('Concurrency must be one or two')
        self.concurrency=concurrency
        self.executor, self.clock = executor, clock
        directory = Path(data_dir)
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or (directory/'intelligence.sqlite3').is_symlink():
            raise PolicyError('Linked intelligence storage is prohibited')
        if (directory/'worker.lock').is_symlink():raise PolicyError('Linked worker lock is prohibited')
        self.lease=(directory/'worker.lock').open('a+b')
        try:
            if self.lease.seek(0,2)==0:
                self.lease.write(b'0');self.lease.flush()
            self.lease.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise PolicyError('Another intelligence worker owns this store; close that backend before restarting') from None
        try:
            self.db = sqlite3.connect(directory / 'intelligence.sqlite3')
        except Exception:
            self.lease.close()
            raise
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version>1:
            self.db.close()
            self.lease.close()
            raise PolicyError('Intelligence database belongs to a newer version; restore a matching application')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, project TEXT, id TEXT, body TEXT, PRIMARY KEY(kind,project,id))')
        self.db.execute('PRAGMA user_version=1')
        self.lock = asyncio.Semaphore(concurrency)
        self.scheduler_lock=asyncio.Lock()
        self.closed = False
        for project, identifier, body in self.db.execute("SELECT project,id,body FROM records WHERE kind='job'").fetchall():
            job = json.loads(body)
            if job['state'] == 'running':
                job.update(state='interrupted', failure_class='interrupted')
                self._save('job', project, identifier, job)

    def _project(self, project):
        if not isinstance(project, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', project):
            raise PolicyError('Invalid project')

    def _save(self, kind, project, identifier, value):
        if kind=='job':value['updated']=self.clock()
        self.db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (kind, project, identifier, json.dumps(value, allow_nan=False)))
        if kind in ('trace','configuration','benchmark','model_event','route_event'):
            self.db.execute('DELETE FROM records WHERE kind=? AND project=? AND rowid NOT IN (SELECT rowid FROM records WHERE kind=? AND project=? ORDER BY rowid DESC LIMIT 200)',(kind,project,kind,project))
        self.db.commit()
        return value

    def _get(self, kind, project, identifier):
        self._project(project)
        row = self.db.execute('SELECT body FROM records WHERE kind=? AND project=? AND id=?', (kind, project, identifier)).fetchone()
        if not row:
            raise PolicyError('Record not found in project')
        return json.loads(row[0])

    def _list(self, kind, project):
        self._project(project)
        limit=400 if kind=='job' else 200
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM records WHERE kind=? AND project=? ORDER BY rowid DESC LIMIT ?', (kind, project,limit))]

    def create(self, project, title, plan, *, timeout=30):
        self._project(project)
        if not isinstance(title, str) or not title.strip() or len(title) > 500:
            raise PolicyError('A bounded title is required')
        if not isinstance(plan, list) or not 1 <= len(plan) <= 12:
            raise PolicyError('Plans require 1 to 12 steps')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not .01 <= timeout <= 120:
            raise PolicyError('Invalid step timeout')
        for index, step in enumerate(plan):
            if not isinstance(step, dict) or set(step) - {'action', 'args', 'depends'} or step.get('action') not in self.ACTIONS:
                raise PolicyError('Tool is outside the runtime allowlist')
            if not isinstance(step.get('args'), dict) or not isinstance(step.get('depends', []), list):
                raise PolicyError('Invalid step arguments or dependencies')
            if any(type(dep) is not int or dep < 0 or dep >= index for dep in step.get('depends', [])):
                raise PolicyError('Dependencies must refer to earlier steps')
        try:
            encoded = json.dumps(plan, sort_keys=True, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise PolicyError('Plan must contain JSON values') from error
        if len(encoded) > 32000:
            raise PolicyError('Plan exceeds size limit')
        if sum(job['state']!='archived' for job in self.jobs(project))>=200:
            raise PolicyError('Project workload limit reached')
        job = dict(id=uuid.uuid4().hex, title=title.strip(), plan=json.loads(encoded), plan_hash=hashlib.sha256(encoded.encode()).hexdigest(), state='awaiting_approval', cursor=0, results=[], timeout=timeout, approved=False, created=self.clock())
        return self._save('job', project, job['id'], job)

    def get(self, project, identifier):
        return self._get('job', project, identifier)

    def jobs(self, project):
        return self._list('job', project)

    def authorize(self, project, identifier, plan_hash, *, approved=False):
        job = self.get(project, identifier)
        if approved is not True or plan_hash != job['plan_hash'] or job['state'] != 'awaiting_approval':
            raise PolicyError('Explicit approval of the current plan is required')
        job.update(approved=True, state='ready')
        return self._save('job', project, identifier, job)

    def cancel(self, project, identifier):
        job = self.get(project, identifier)
        if job['state'] in ('completed','archived'):
            raise PolicyError('Terminal workloads can be archived, not cancelled')
        job['state'] = 'cancelled'
        return self._save('job', project, identifier, job)

    def archive(self,project,identifier,*,approved=False):
        job=self.get(project,identifier)
        if approved is not True or job['state'] not in ('completed','failed','cancelled'):
            raise PolicyError('Explicit approval and a terminal workload are required')
        job.update(archived_state=job['state'],state='archived')
        self._save('job',project,identifier,job)
        archived=[item for item in self.jobs(project) if item['state']=='archived']
        for item in archived[200:]:
            self.db.execute("DELETE FROM records WHERE kind='job' AND project=? AND id=?",(project,item['id']))
        self.db.commit()
        return job

    def resume(self, project, identifier, *, approved=False):
        job = self.get(project, identifier)
        if approved is not True or not job['approved'] or job['state'] not in ('cancelled', 'interrupted', 'failed'):
            raise PolicyError('Explicit resume approval is required')
        job.update(state='ready', failure_class=None)
        return self._save('job', project, identifier, job)

    async def run(self, project, identifier, *, max_steps=12):
        if type(max_steps) is not int or not 1 <= max_steps <= 12:
            raise PolicyError('Invalid execution budget')
        async with self.lock:
            job = self.get(project, identifier)
            if job['state'] == 'completed':
                return job
            if not job['approved'] or job['state'] != 'ready':
                raise PolicyError('Job requires approval or explicit resume')
            for _ in range(max_steps):
                index = job['cursor']
                if index >= len(job['plan']):
                    break
                step = job['plan'][index]
                job['state'] = 'running'
                self._save('job', project, identifier, job)
                start = self.clock()
                failure = None
                try:
                    result = await asyncio.wait_for(self.executor(step['action'], step['args'], project), job['timeout'])
                    verified = isinstance(result, dict) and result.get('ok') is True
                    if not verified:
                        failure = 'unverified_result'
                    if len(json.dumps(result, allow_nan=False))>64000:
                        raise ValueError('Tool result exceeds checkpoint limit')
                except asyncio.CancelledError:
                    job.update(state='interrupted', failure_class='cancelled_execution')
                    self._save('job', project, identifier, job)
                    raise
                except Exception as error:
                    failure = 'timeout' if isinstance(error, TimeoutError) else 'execution_error'
                    result, verified = {'ok': False, 'error': failure}, False
                trace = dict(id=uuid.uuid4().hex, job_id=identifier, step=index, action=step['action'], result=result, verified=verified, failure_class=failure, elapsed=max(0, self.clock()-start))
                self._save('trace', project, trace['id'], trace)
                # A cancellation received during the await is authoritative.
                current = self.get(project, identifier)
                job['results'].append(result)
                if verified:
                    job['cursor'] += 1
                job.update(state='ready' if verified else 'failed', failure_class=failure)
                if current['state'] == 'cancelled':
                    job['state'] = 'cancelled'
                if job['cursor'] == len(job['plan']) and job['state'] == 'ready':
                    job['state'] = 'completed'
                self._save('job', project, identifier, job)
                if job['state'] != 'ready':
                    break
            return job

    def traces(self, project):
        return self._list('trace', project)

    def configure_scheduler(self, enabled, *, approved=False):
        if approved is not True or type(enabled) is not bool:
            raise PolicyError('Explicit scheduler approval is required')
        self._save('setting', 'system', 'scheduler', {'enabled': enabled})
        snapshot={'id':uuid.uuid4().hex,'version':1,'enabled':enabled,'created':self.clock()}
        self._save('configuration','system',snapshot['id'],snapshot)

    def configurations(self):
        return self._list('configuration','system')

    def restore_configuration(self,identifier,*,approved=False):
        if approved is not True:raise PolicyError('Explicit configuration restore approval is required')
        snapshot=self._get('configuration','system',identifier)
        if snapshot.get('version')!=1:raise PolicyError('Unsupported configuration version')
        self.configure_scheduler(snapshot['enabled'],approved=True)
        return snapshot

    def _cron_next(self, expression, timezone):
        try:
            from croniter import croniter
        except ImportError:
            raise PolicyError('Cron scheduling requires optional requirements-intelligence.txt; once and interval schedules remain available') from None
        if not isinstance(expression,str) or len(expression)>100 or len(expression.split())!=5 or not isinstance(timezone,str) or len(timezone)>80:
            raise PolicyError('Use a five-field cron expression and an IANA timezone')
        try:
            return croniter(expression,datetime.fromtimestamp(self.clock(),ZoneInfo(timezone)),max_years_between_matches=2).get_next(float)
        except Exception:
            raise PolicyError('Invalid or unreachable cron expression or timezone') from None

    def schedule(self, project, identifier, specification, *, approved=False):
        job = self.get(project, identifier)
        if approved is not True or not job['approved'] or job['state'] != 'ready':
            raise PolicyError('Approve the job before scheduling')
        if not isinstance(specification, dict):
            raise PolicyError('Invalid schedule')
        kind = specification.get('kind')
        if kind == 'once' and set(specification) == {'kind', 'at'}:
            at = specification['at']
        elif kind == 'interval' and set(specification) == {'kind', 'seconds'}:
            seconds = specification['seconds']
            if type(seconds) is not int or not 60 <= seconds <= 31536000:
                raise PolicyError('Interval must be between 60 seconds and one year')
            at = self.clock() + seconds
        elif kind=='cron' and set(specification)=={'kind','expression','timezone'}:
            at=self._cron_next(specification['expression'],specification['timezone'])
        else:
            raise PolicyError('Unsupported schedule specification')
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at) or at < self.clock():
            raise PolicyError('Schedule must be in the future')
        value = dict(id=uuid.uuid4().hex, project=project, job_id=identifier, kind=kind, at=at, enabled=True, seconds=specification.get('seconds'),expression=specification.get('expression'),timezone=specification.get('timezone'))
        return self._save('schedule', project, value['id'], value)

    def schedules(self, project):
        return self._list('schedule', project)

    async def tick(self):
        async with self.scheduler_lock:
            return await self._tick()

    async def _tick(self):
        try:
            enabled = self._get('setting', 'system', 'scheduler')['enabled']
        except PolicyError:
            enabled = False
        if not enabled:
            return []
        due = [json.loads(row[0]) for row in self.db.execute("SELECT body FROM records WHERE kind='schedule'").fetchall()]
        results = []
        for schedule in due:
            if not self._get('setting','system','scheduler')['enabled']:break
            if schedule['enabled'] and schedule['at'] <= self.clock():
                # Reserve durably before any effect. A crash never replays a claim.
                schedule['enabled'] = False
                self._save('schedule', schedule['project'], schedule['id'], schedule)
                try:
                    results.append(await self.run(schedule['project'], schedule['job_id']))
                except PolicyError:
                    continue
                if schedule['kind'] in ('interval','cron'):
                    job = self.get(schedule['project'], schedule['job_id'])
                    if job['state'] == 'completed':
                        job.update(state='ready', cursor=0, results=[])
                        self._save('job', schedule['project'], job['id'], job)
                        next_at=self.clock()+schedule['seconds'] if schedule['kind']=='interval' else self._cron_next(schedule['expression'],schedule['timezone'])
                        schedule.update(enabled=True, at=next_at)
                        self._save('schedule', schedule['project'], schedule['id'], schedule)
        return results

    async def close(self):
        self.close_storage()

    def close_storage(self):
        if not self.closed:
            self.db.close()
            self.lease.close()
            self.closed = True
