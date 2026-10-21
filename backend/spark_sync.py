"""Pull-only, bounded integration snapshots. Never invokes provider write tools."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from spark_productivity import WorkbenchError

# Closed host policy: new MCP tools are never automatically scheduled.
READS = {
    'gmail':['google_daily_briefing','google_list_items'],
    'google-drive':['google_daily_briefing','google_list_items'],
    'google-calendar':['google_daily_briefing','google_list_items'],
    'slack':['slack_list_channels'],
    'github':['github_repository_status','github_list_pull_requests','github_list_issues'],
    'hermes':['hermes_learned_skills','hermes_memory_cards'],
    'graphiti':['graph_status'],
    'vyndi-os':['read_vyndi_engineering_authority'], 'vedm':['read_vedm_library'],
    'vaos-jarvis':['ask_vaos_jarvis'],
}
MAX_BYTES=1_000_000


def safe_data(value, depth=0):
    if depth>30: raise ValueError('Snapshot nesting limit.')
    if isinstance(value,dict):
        return {k:safe_data(v,depth+1) for k,v in value.items()
                if not any(word in k.lower() for word in ('token','secret','password','cookie','authorization','headers'))}
    if isinstance(value,list): return [safe_data(v,depth+1) for v in value]
    return value


class IntegrationSync:
    def __init__(self, root, integrations, *, clock=time.time, local=None, authorized=lambda:True):
        self.root=Path(root)/'integration-sync'
        self.integrations=integrations
        self.clock=clock
        self.local=local
        self.authorized=authorized
        self.lock=asyncio.Lock()
        self.runner=None
        self.task=None
        self.closed=False
        self.wake=asyncio.Event()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,enabled INTEGER,interval INTEGER)')
            db.execute('INSERT OR IGNORE INTO settings VALUES(1,?,300)',(os.environ.get('SPARK_AUTO_SYNC_ENABLED')=='1',))
            db.execute('CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,service TEXT,tool TEXT,mode TEXT,body TEXT,digest TEXT,version INTEGER DEFAULT 0,last_success REAL,last_attempt REAL,next_due REAL DEFAULT 0,failures INTEGER DEFAULT 0,state TEXT,error TEXT)')

    @contextmanager
    def db(self):
        if self.root.is_symlink(): raise WorkbenchError('Linked sync storage is prohibited.')
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.root/'snapshots.sqlite3'
        if path.is_symlink(): raise WorkbenchError('Linked sync storage is prohibited.')
        db=sqlite3.connect(path,timeout=5)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def settings(self):
        with self.db() as db: row=db.execute('SELECT enabled,interval FROM settings WHERE id=1').fetchone()
        return {'enabled':bool(row['enabled']),'interval_seconds':row['interval']}

    def configure(self,enabled,interval_seconds):
        if type(enabled) is not bool or type(interval_seconds) is not int or not 60<=interval_seconds<=3600:
            raise WorkbenchError('Choose automatic sync and an interval from 60 to 3600 seconds.')
        with self.db() as db: db.execute('UPDATE settings SET enabled=?,interval=? WHERE id=1',(enabled,interval_seconds))
        self.wake.set()
        return self.status()

    def plan(self):
        result=[]
        for item in self.integrations.list():
            if not item.get('configured'): continue
            service=item['name']; approved=item.get('read_tools',[])
            tools=[tool for tool in READS.get(service,[]) if tool in approved]
            # Prefer a meaningful structured read over the legacy IDs-only list.
            if service in ('gmail','google-calendar','google-drive') and 'google_daily_briefing' in tools:
                tools=['google_daily_briefing']
            for tool in tools:
                result.append((service,tool,'status' if service=='graphiti' else 'data'))
            if not tools: result.append((service,'__catalog__','status'))
        if self.local is not None: result.append(('obsidian','vault_notes','data'))
        result.append(('connections','connection_status','status'))
        return result

    def status(self):
        planned=self.plan()
        settings=self.settings()
        with self.db() as db: stored={row['id']:dict(row) for row in db.execute('SELECT id,state,last_success,last_attempt,next_due,version,error FROM snapshots')}
        rows=[]
        for service,tool,mode in planned:
            row=stored.get(service+'/'+tool,{})
            rows.append({'id':service+'/'+tool,'service':service,'tool':tool,'mode':mode,
                'state':row.get('state','waiting'),'last_success':row.get('last_success'),
                'last_attempt':row.get('last_attempt'),'next_due':row.get('next_due'),
                'version':row.get('version',0),'error':row.get('error'),
                'stale':not row.get('last_success') or self.clock()-row['last_success']>2*max(settings['interval_seconds'],900 if service=='vaos-jarvis' else 0)})
        return {**settings,'running':self.lock.locked() or bool(self.task and not self.task.done()),'scope':'read-only local snapshots while Spark is open',
                'limit':'Existing bounded readers only: recent items or reference data; not full account backups.',
                'sources':rows}

    def cached(self,identity):
        allowed={s+'/'+t for s,t,_ in self.plan()}
        if identity not in allowed: raise WorkbenchError('Select a connected synchronization source.')
        with self.db() as db: row=db.execute('SELECT body,last_success,state FROM snapshots WHERE id=?',(identity,)).fetchone()
        return {'id':identity,'data':json.loads(row['body']) if row and row['body'] else None,
                'last_success':row['last_success'] if row else None,'state':row['state'] if row else 'waiting',
                'untrusted_source':True}

    def search(self,query):
        if not isinstance(query,str) or not 1<=len(query.strip())<=200: raise WorkbenchError('Enter a search of 1–200 characters.')
        allowed={s+'/'+t for s,t,_ in self.plan()}; hits=[]
        with self.db() as db:
            for row in db.execute('SELECT id,service,body,last_success,state FROM snapshots WHERE body IS NOT NULL'):
                if row['id'] not in allowed: continue
                text=row['body']; index=text.lower().find(query.strip().lower())
                if index>=0: hits.append({'id':row['id'],'service':row['service'],'last_success':row['last_success'],
                    'state':row['state'],'snippet':text[max(0,index-100):index+500],'untrusted_source':True})
        return {'results':hits[:20],'mode':'local integration cache'}

    def briefing(self):
        """Read the latest LOCAL snapshots; never silently claim this is a live read."""
        status = self.status()
        now = self.clock()
        today = datetime.fromtimestamp(now, ZoneInfo('Asia/Kolkata')).date().isoformat()
        sources = {}
        results = {'gmail': [], 'google-calendar': [], 'google-drive': []}
        fields = {'gmail': 'messages', 'google-calendar': 'events',
                  'google-drive': 'files'}
        for service in fields:
            rows = [item for item in status['sources'] if item['service'] == service]
            item = next((row for row in rows
                         if row['tool'] == 'google_daily_briefing'), None)
            if not item:
                sources[service] = {
                    'state': 'not_configured' if not rows else 'upgrade_required',
                    'message': ('Register the read-only google_daily_briefing MCP tool '
                                'for this Google service. Connection alone is insufficient.')}
                continue
            source = {
                'state': item['state'], 'last_success': item['last_success'],
                'stale': item['stale'], 'error': item.get('error'),
                'mode': 'cached, read-only', 'message': None}
            if not item['last_success']:
                source['message'] = 'No verified read yet. Select Refresh now.'
                sources[service] = source
                continue
            try:
                cached = self.cached(item['id'])['data']
                data = cached.get('data') if isinstance(cached, dict) else None
                if not isinstance(data, dict) or data.get('source') != service:
                    raise ValueError('Unsupported cached source.')
                value = data.get(fields[service], [])
                if not isinstance(value, list):
                    raise ValueError('Invalid cached items.')
                results[service] = value
                source['possibly_truncated'] = bool(data.get('possibly_truncated'))
                source['note'] = data.get('note')
                source['account'] = cached.get('account')
                if service == 'gmail' and data.get('date') != today:
                    source['state'] = 'outdated'
                    source['message'] = 'Cached email window is from a different day. Refresh now.'
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                source['state'] = 'invalid'
                source['message'] = 'Cached response cannot be interpreted.'
            sources[service] = source
        return {'timezone': 'Asia/Kolkata', 'date': today,
                'generated_at': now, 'mode': 'cached Google reads, not live',
                'sources': sources,
                'emails': results['gmail'], 'events': results['google-calendar'],
                'documents': results['google-drive'],
                'attention_count': sum(mail.get('priority') in ('urgent', 'action')
                                       for mail in results['gmail']
                                       if isinstance(mail, dict)),
                'read_only': True}

    async def pull(self,service,tool):
        if service=='obsidian': return await asyncio.to_thread(self.local)
        if service=='connections':
            from spark_connectivity import Connectivity
            return await Connectivity(integrations=self.integrations).report(deep=False)
        if tool=='__catalog__':
            tools=await self.integrations.execute(service,'mcp_discover',{})
            return {'tools':[{'name':v.get('name')} for v in tools],'scope':'tool availability only; no data feed'}
        arguments={'question':'What is the current digital workforce status? Preserve missing evidence and release holds.'} if service=='vaos-jarvis' else {}
        response=await self.integrations.execute(service,'mcp_call',{'name':tool,'arguments':arguments})
        if response.get('isError'): raise ValueError('Provider read failed.')
        if isinstance(response.get('structuredContent'),dict): value=response['structuredContent']
        else:
            parts=[v['text'] for v in response.get('content',[]) if v.get('type')=='text']
            if not parts: raise ValueError('Empty provider read.')
            value=json.loads(parts[0])
        if not isinstance(value,(dict,list)) or isinstance(value,dict) and value.get('ok') is False:
            raise ValueError('Provider read failed.')
        return value

    async def cycle(self,force=False):
        if self.lock.locked(): return self.status()
        async with self.lock:
            for service,tool,mode in self.plan():
                if self.closed or not self.authorized() or (not force and not self.settings()['enabled']): break
                identity=service+'/'+tool; now=self.clock()
                with self.db() as db: old=db.execute('SELECT * FROM snapshots WHERE id=?',(identity,)).fetchone()
                if old and now<old['next_due']: continue # Manual refresh also honors failure backoff.
                try:
                    value=await asyncio.wait_for(self.pull(service,tool),timeout=155)
                    body=json.dumps(safe_data(value),ensure_ascii=False,sort_keys=True,allow_nan=False)
                    if len(body.encode('utf-8'))>MAX_BYTES: raise ValueError('Snapshot too large.')
                    digest=hashlib.sha256(body.encode('utf-8')).hexdigest()
                    version=(old['version'] if old else 0)+(not old or old['digest']!=digest)
                    with self.db() as db:
                        db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (identity,service,tool,mode,body,digest,version,self.clock(),now,
                             self.clock()+max(self.settings()['interval_seconds'],900 if service=='vaos-jarvis' else 0),0,'current',None))
                except asyncio.CancelledError: raise
                except Exception:
                    failures=min((old['failures'] if old else 0)+1,8)
                    due=self.clock()+min(3600,self.settings()['interval_seconds']*2**(failures-1))
                    with self.db() as db:
                        db.execute('INSERT INTO snapshots(id,service,tool,mode,last_attempt,next_due,failures,state,error) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_attempt=excluded.last_attempt,next_due=excluded.next_due,failures=excluded.failures,state=excluded.state,error=excluded.error',
                            (identity,service,tool,mode,now,due,failures,'failed','Read unavailable; check source sign-in and permissions. Previous snapshot retained.'))
        return self.status()

    async def start(self):
        if self.runner is None or self.runner.done():
            self.closed=False
            self.runner=asyncio.create_task(self.run())

    async def run(self):
        while not self.closed:
            try:
                if self.settings()['enabled'] and self.authorized(): await self.cycle()
            except asyncio.CancelledError: raise
            except Exception: pass # One unavailable source must not stop voice or the next scheduled cycle.
            self.wake.clear()
            try: await asyncio.wait_for(self.wake.wait(),timeout=30)
            except asyncio.TimeoutError: pass

    async def close(self):
        self.closed=True
        tasks=[t for t in (self.runner,self.task) if t and not t.done()]
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks,return_exceptions=True)

    async def execute(self,action,data):
        keys={'sync_status':set(),'sync_configure':{'enabled','interval_seconds'},'sync_now':set(),
              'sync_cached':{'id'},'sync_search':{'query'},'sync_briefing':set()}
        if action not in keys or not isinstance(data,dict) or set(data)!=keys[action]: raise WorkbenchError('Invalid synchronization request.')
        if action=='sync_configure': return self.configure(**data)
        if action=='sync_cached': return self.cached(data['id'])
        if action=='sync_briefing': return self.briefing()
        if action=='sync_search': return self.search(data['query'])
        if action=='sync_now':
            # Refresh successful sources now; failed sources keep their backoff.
            with self.db() as db: db.execute("UPDATE snapshots SET next_due=0 WHERE state='current' AND service!='vaos-jarvis'")
            if self.task is None or self.task.done(): self.task=asyncio.create_task(self.cycle(force=True))
        return self.status()
