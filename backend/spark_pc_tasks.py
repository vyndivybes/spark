"""Durable PC tasks bound to explicit review of the exact proposed plan."""
import asyncio
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from contextlib import contextmanager
from spark_pc_access import PC_TOOL

PC_TASK_ACTIONS={
    'pc_task_prepare':{'goal','advice','steps'},
    'pc_task_run':{'id','plan_hash','approved'},
    'pc_task_history':set(),
}


class PcTasks:
    def __init__(self,root):
        self.root=Path(root)
        self.lock=threading.RLock()
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink() or (self.root/'tasks.sqlite3').is_symlink():
            raise ValueError('Linked PC task storage is not allowed.')
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,project TEXT,body TEXT)')
            for identity,body in db.execute('SELECT id,body FROM tasks'):
                value=json.loads(body)
                if value['state']=='running':
                    value['state']='interrupted'
                    db.execute('UPDATE tasks SET body=? WHERE id=?',(json.dumps(value),identity))

    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.root/'tasks.sqlite3')
        try:
            with db:yield db
        finally:db.close()

    def _load(self,db,project,identity):
        row=db.execute('SELECT body FROM tasks WHERE project=? AND id=?',(project,identity)).fetchone()
        if not row:raise ValueError('PC task not found in this project.')
        return json.loads(row[0])

    def _save(self,db,value):
        db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?)',(value['id'],value['project'],json.dumps(value)))

    def prepare(self,project,goal,advice,steps):
        if not isinstance(goal,str) or not 3<=len(goal.strip())<=500 or not isinstance(advice,str) or not 1<=len(advice)<=16000:
            raise ValueError('Provide a task goal and a bounded Jarvis advisory.')
        if steps is None:
            destination=Path.home()/'Documents'/'SPARK'/'Advisories'/(time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.md')
            steps=[{'action':'write','path':str(destination),'content':'# '+goal.strip()+'\n\nVAOS advisory, not execution authority.\n\n'+advice}]
        required={'list':{'path'},'read':{'path'},'write':{'path','content'},'mkdir':{'path'},
                  'copy':{'path','destination'},'move':{'path','destination'},'run':{'command'},'launch':{'path'}}
        if not isinstance(steps,list) or not 1<=len(steps)<=6:raise ValueError('Use one to six PC actions.')
        for step in steps:
            if not isinstance(step,dict) or step.get('action') not in required or set(step)-set(PC_TOOL['parameters']['properties']) or not required[step['action']]<=set(step):
                raise ValueError('Each step must be a valid PC action with its required fields.')
            for key in required[step['action']]:
                if not isinstance(step[key],str) or (key!='content' and not step[key].strip()):raise ValueError('Required action values must be text.')
            for key in ('path','destination','content','command','cwd'):
                if key in step and not isinstance(step[key],str):raise ValueError('Action text fields must be strings.')
            if 'timeout' in step and (type(step['timeout']) is not int or not 1<=step['timeout']<=120):raise ValueError('Command timeout must be 1 to 120 seconds.')
            if 'offset' in step and (type(step['offset']) is not int or step['offset']<0):raise ValueError('Read offset must be nonnegative.')
            if 'arguments' in step and (not isinstance(step['arguments'],list) or any(not isinstance(arg,str) for arg in step['arguments'])):raise ValueError('Program arguments must be a string array.')
        frozen=json.loads(json.dumps(steps))
        if len(json.dumps(frozen))>100000:raise ValueError('PC plan exceeds 100 KB.')
        digest=hashlib.sha256(json.dumps({'goal':goal,'advice':advice,'steps':frozen},sort_keys=True).encode()).hexdigest()
        value={'id':secrets.token_hex(12),'project':project,'goal':goal,'advice':advice,'steps':frozen,
               'plan_hash':digest,'state':'awaiting_approval','created_at':time.time(),'results':[]}
        with self.lock,self._db() as db:self._save(db,value)
        return value

    def history(self,project):
        with self.lock,self._db() as db:
            values=[json.loads(row[0]) for row in db.execute('SELECT body FROM tasks WHERE project=? ORDER BY rowid DESC LIMIT 30',(project,))]
            return [{key:value[key] for key in ('id','project','goal','state','created_at')} for value in values]

    def run(self,project,identity,plan_hash,approved,access):
        with self.lock,self._db() as db:
            value=self._load(db,project,identity)
            if approved is not True or plan_hash!=value['plan_hash']:raise ValueError('Approve the exact staged PC plan.')
            if value['state'] in ('completed','failed','interrupted'):return value
            if value['state']!='awaiting_approval':raise ValueError('PC task is already running.')
            if not access or not access.enabled():raise ValueError('Enable PC autonomy in the active authenticated session.')
            value['state']='running';self._save(db,value)
        for step in value['steps']:
            result=access.execute(step)
            value['results'].append(result)
            value['state']='running' if result.get('ok') else 'failed'
            with self.lock,self._db() as db:self._save(db,value)
            if not result.get('ok'):break
        if value['state']=='running':value['state']='completed'
        with self.lock,self._db() as db:self._save(db,value)
        return value

    async def execute(self,action,project,payload,access):
        if action not in PC_TASK_ACTIONS or not isinstance(payload,dict) or set(payload)!=PC_TASK_ACTIONS[action]:raise ValueError('Invalid PC task request.')
        if action=='pc_task_prepare':return await asyncio.to_thread(self.prepare,project,**payload)
        if action=='pc_task_history':return await asyncio.to_thread(self.history,project)
        return await asyncio.to_thread(self.run,project,payload['id'],payload['plan_hash'],payload['approved'],access)
