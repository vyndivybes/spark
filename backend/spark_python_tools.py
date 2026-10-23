"""Trusted full-Python tools. Runs as the local OS user; not an OS sandbox."""
import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time

if sys.argv[1:]==['--worker']:
    sys.path.insert(0,str(Path(__file__).resolve().parent))

from spark_maintenance import atomic_write
from spark_code_skills import CodeSkillError,bounded

GATEWAY_NAME='spark_generated_tool'
GATEWAY={'name':GATEWAY_NAME,'description':'Discover, invent and execute active Spark Python tools. List tools first for specialized tasks. Forge a missing capability only when the user requests it; report actual test/run results. Newly activated tools are available immediately.',
 'parameters':{'type':'OBJECT','properties':{'action':{'type':'STRING','enum':['list','forge','run']},'goal':{'type':'STRING'},'name':{'type':'STRING'},'input_json':{'type':'STRING','description':'JSON input object/value for run'}},'required':['action']}}


def openai_gateway():
    def convert(value):
        if isinstance(value,dict):return {k:(v.lower() if k=="type" and isinstance(v,str) else convert(v)) for k,v in value.items()}
        if isinstance(value,list):return [convert(v) for v in value]
        return value
    return convert(GATEWAY)


def generated_live_config(config,gateway):
    if gateway is None or not gateway.enabled():return config
    import copy
    result=copy.deepcopy(config if isinstance(config,dict) else config.model_dump(exclude_none=True))
    result.setdefault('tools',[]).append({'function_declarations':[GATEWAY]})
    instruction=result.get('system_instruction','')
    if not isinstance(instruction,str):instruction='You are Spark.'
    result['system_instruction']=instruction.replace('No tools are provided in cinematic voice mode.','')+' Use spark_generated_tool to list specialized active tools, forge a missing requested capability, and run it. Read tool results; never invent completion. Newly created tools are visible through list/run immediately.'
    return result


class PythonTools:
    def __init__(self,root):
        self.root=Path(root)/'python-tools';self.lock=threading.RLock();self.workers=set();self.worker_lock=threading.Lock()
    def policy(self):
        path=self.root/'policy.json'
        if path.is_symlink() or self.root.is_symlink():raise CodeSkillError('Linked tool policy prohibited.')
        try:
            value=json.loads(path.read_text()) if path.exists() else {'enabled':False,'auto_forge':False}
            if not isinstance(value,dict) or type(value.get('enabled'))is not bool or type(value.get('auto_forge'))is not bool:return {'enabled':False,'auto_forge':False}
            return value
        except (OSError,ValueError):return {'enabled':False,'auto_forge':False}
    def configure(self,enabled,auto_forge):
        if type(enabled)is not bool or type(auto_forge)is not bool:raise CodeSkillError('Tool policy values must be booleans.')
        self.policy();record={'enabled':enabled,'auto_forge':enabled and auto_forge}
        if not enabled:
            with self.worker_lock:
                for process in tuple(self.workers):
                    if process.poll() is None:process.terminate()
        atomic_write(self.root/'policy.json',json.dumps(record).encode());return record
    def _path(self,project):
        if not isinstance(project,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',project):raise CodeSkillError('Invalid project.')
        path=self.root/(project+'.json')
        if path.is_symlink() or self.root.is_symlink():raise CodeSkillError('Linked tool storage prohibited.')
        return path
    def list(self,project):
        with self.lock:
            path=self._path(project);return json.loads(path.read_text()) if path.exists() else []
    def _save(self,project,rows):atomic_write(self._path(project),json.dumps(rows).encode())
    def propose(self,project,spec):
        if not isinstance(spec,dict) or set(spec)!={'name','description','source','tests','requirements','environment'}:raise CodeSkillError('Invalid Python tool specification.')
        if not isinstance(spec['name'],str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,31}',spec['name']):raise CodeSkillError('Invalid tool name.')
        if not isinstance(spec['description'],str) or not 1<=len(spec['description'])<=300:raise CodeSkillError('Invalid description.')
        if not isinstance(spec['source'],str) or len(spec['source'].encode())>16000:raise CodeSkillError('Tool source exceeds 16 KB.')
        try:
            tree=ast.parse(spec['source']);compile(tree,'generated-tool','exec')
            if not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='run' for n in tree.body):raise ValueError()
        except (ValueError,SyntaxError):raise CodeSkillError('Tool must define valid Python run(inputs).') from None
        from spark_security_scan import scan_secrets
        if scan_secrets(spec['source'],'python-tool'):raise CodeSkillError('Remove embedded credentials; declare environment names instead.')
        for field,pattern,maximum in [('requirements',r'[A-Za-z0-9][A-Za-z0-9_.-]*(?:==[A-Za-z0-9_.+-]+)?',8),('environment',r'[A-Z][A-Z0-9_]{1,70}',12)]:
            value=spec[field]
            if not isinstance(value,list) or len(value)>maximum or any(not isinstance(x,str) or not re.fullmatch(pattern,x) for x in value):raise CodeSkillError('Invalid '+field)
        cases=spec['tests']
        if not isinstance(cases,list) or not 2<=len(cases)<=12 or any(not isinstance(c,dict) or set(c)!={'inputs','expected'} for c in cases):raise CodeSkillError('Provide 2–12 independent expected-result cases.')
        bounded(cases)
        if len({json.dumps(c["inputs"],sort_keys=True) for c in cases})<2:raise CodeSkillError("Use distinct test inputs.")
        with self.lock:
            rows=self.list(project)
            if len(rows)>=80:raise CodeSkillError('Tool revision limit reached.')
            record={**spec,'id':secrets.token_hex(12),'runtime':'python','status':'proposed','sha256':hashlib.sha256(spec['source'].encode()).hexdigest()}
            rows.append(record);self._save(project,rows);return record
    def _python(self,record,install=False):
        if not record['requirements']:return sys.executable
        folder=self.root/'environments'/record['id']
        binary=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if not binary.exists():
            if not install:raise CodeSkillError('Approve package environment preparation first.')
            subprocess.run([sys.executable,'-m','venv',str(folder)],check=True,timeout=90,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        marker=folder/'spark-requirements.json'
        if not marker.exists() or json.loads(marker.read_text())!=record['requirements']:
            if not install:raise CodeSkillError('Tool package environment is not prepared.')
            subprocess.run([str(binary),'-m','pip','install','--disable-pip-version-check',*record['requirements']],check=True,timeout=180,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            atomic_write(marker,json.dumps(record['requirements']).encode())
        return str(binary)
    def _run(self,record,inputs):
        if hashlib.sha256(record['source'].encode()).hexdigest()!=record['sha256']:raise CodeSkillError('Tool source integrity changed.')
        bounded(inputs)
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PATH'}}
        env.update({key:os.environ[key] for key in record['environment'] if key in os.environ})
        folder=self.root/'work'/record['id'];folder.mkdir(parents=True,exist_ok=True)
        try:
            process=subprocess.Popen([self._python(record),'-I',str(Path(__file__).resolve()),'--worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=folder,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            with self.worker_lock:self.workers.add(process)
            try:
                if not self.policy()['enabled']:
                    process.terminate();raise CodeSkillError('Tool execution stopped.')
                stdout,stderr=process.communicate(json.dumps({'source':record['source'],'inputs':inputs}),timeout=30)
            except subprocess.TimeoutExpired:
                process.kill();process.communicate();raise CodeSkillError('Python tool exceeded thirty seconds.') from None
            finally:
                with self.worker_lock:self.workers.discard(process)
            if process.returncode:raise CodeSkillError('Python tool worker failed or was stopped.')
            reply=json.loads(stdout.splitlines()[-1])
            if not reply.get('ok'):raise CodeSkillError(reply.get('error','Tool failed.'))
            def redact(value):
                if isinstance(value,dict):return {k:('[redacted]' if k.lower() in {'password','secret','token','authorization','api_key','access_token'} else redact(v)) for k,v in value.items()}
                if isinstance(value,list):return [redact(v) for v in value]
                if isinstance(value,str):
                    for key in record['environment']:
                        secret=os.environ.get(key,'')
                        if len(secret)>=8 and any(part in key for part in ('KEY','TOKEN','PASSWORD','SECRET')):value=value.replace(secret,'[redacted]')
                return value
            return bounded(redact(reply['result']))
        except (subprocess.SubprocessError,OSError,ValueError,IndexError) as error:
            raise CodeSkillError('Python tool failed or exceeded its execution limit: '+type(error).__name__) from None
    def action(self,project,action,identity,approved=False,inputs=None):
        if not self.policy()['enabled']:raise CodeSkillError('Full Python tools are disabled.')
        with self.lock:
            rows=self.list(project);record=next((r for r in rows if r['id']==identity),None)
            if record is None:raise CodeSkillError('Unknown Python tool revision.')
            if action=='test':
                if approved is not True:raise CodeSkillError('Approve Python execution and declared packages/API environment first.')
                self._python(record,install=True)
                checks=[]
                for case in record['tests']:
                    try:
                        actual=self._run(record,case['inputs']);checks.append({'passed':actual==case['expected'],'actual':actual})
                    except CodeSkillError:checks.append({'passed':False})
                record['test_results']=checks;record['status']='tested' if all(c['passed'] for c in checks) else 'rejected'
            elif action=='activate':
                if approved is not True or record['status']!='tested':raise CodeSkillError('Only reviewed, tested tools can activate.')
                if any(self._run(record,c['inputs'])!=c['expected'] for c in record['tests']):raise CodeSkillError('Activation test failed.')
                for row in rows:
                    if row['name']==record['name'] and row['status']=='active':row['status']='inactive'
                record['status']='active'
            elif action=='deactivate':record['status']='inactive'
            elif action=='run':
                if record['status']!='active':raise CodeSkillError('Tool is not active.')
                return {'id':identity,'name':record['name'],'result':self._run(record,inputs)}
            else:raise CodeSkillError('Unknown tool operation.')
            self._save(project,rows);return record


class GeneratedToolGateway:
    def __init__(self,evolution,project,emit=None,authorized=lambda:True):
        self.evolution=evolution;self.project=project;self.emit=emit;self.authorized=authorized
        self.previous_tools={}
    def enabled(self):return self.authorized() and self.evolution.python_tools.policy()['enabled']
    async def call(self,arguments):
        if not self.enabled():return {'ok':False,'error':'Generated tools disabled or session authorization expired.'}
        project=self.project() if callable(self.project) else self.project
        async def progress(phase,name=''):
            if self.emit:await self.emit({'phase':phase,'name':name,'project':project})
        try:
            action=arguments.get('action')
            if action=='list':
                def shape(value,depth=0):
                    if depth>5:return None
                    if isinstance(value,dict):return {k:shape(v,depth+1) for k,v in value.items()}
                    if isinstance(value,list):return [shape(value[0],depth+1)] if value else []
                    if isinstance(value,bool):return False
                    if isinstance(value,(int,float)):return 0
                    return '' if isinstance(value,str) else None
                learning=getattr(self.evolution,'trace_learning',None)
                patterns=await asyncio.to_thread(learning.patterns,project) if learning else []
                active_names={r['name'] for r in self.evolution.python_tools.list(project) if r['status']=='active'}
                patterns=[p for p in patterns if set(p['tool_sequence'])<=active_names]
                return {'ok':True,'learned_workflows':patterns,'tools':[{'name':r['name'],'description':r['description'],'id':r['id'],'input_shape':shape(r['tests'][0]['inputs'])} for r in self.evolution.python_tools.list(project) if r['status']=='active'][:20]}
            if action=='forge':
                if not self.evolution.python_tools.policy()['auto_forge']:raise CodeSkillError('Automatic tool invention is disabled.')
                await progress('generating')
                record=await self.evolution.execute('generate_python_tool',project,{'description':arguments.get('goal','')})
                if record['requirements'] or record['environment']:
                    await progress('review_required',record['name'])
                    return {'ok':True,'status':'review_required','id':record['id'],'message':'Review packages and credential environment in Upgrade Studio before execution.'}
                if not self.enabled():raise CodeSkillError('Tool activity stopped.')
                await progress('testing',record['name'])
                tested=await self.evolution.execute('test_python_tool',project,{'id':record['id'],'approved':True})
                if tested['status']!='tested':
                    await progress('repairing',record['name'])
                    record=await self.evolution.execute('repair_python_tool',project,{'id':record['id']})
                    if not self.enabled():raise CodeSkillError('Tool activity stopped.')
                    await progress('testing',record['name'])
                    tested=await self.evolution.execute('test_python_tool',project,{'id':record['id'],'approved':True})
                    if tested['status']!='tested':raise CodeSkillError('Generated tool failed expected-result tests after one source repair; left inactive.')
                if not self.enabled():raise CodeSkillError('Tool activity stopped.')
                active=await self.evolution.execute('activate_python_tool',project,{'id':record['id'],'approved':True})
                await progress('registered',active['name'])
                return {'ok':True,'status':'active','name':active['name'],'id':active['id'],'example_input':active['tests'][0]['inputs'],'message':'New tool is registered. Call run with its name and JSON inputs.'}
            if action=='run':
                record=next((r for r in self.evolution.python_tools.list(project) if r['name']==arguments.get('name') and r['status']=='active'),None)
                if record is None:raise CodeSkillError('List the active tools and select an exact name.')
                inputs=json.loads(arguments.get('input_json','{}'))
                await progress('running',record['name'])
                names=self.previous_tools.get(project,[])+[record['name']]
                learning=getattr(self.evolution,'trace_learning',None)
                try:
                    result=await self.evolution.execute('run_python_tool',project,{'id':record['id'],'inputs':inputs})
                except Exception:
                    self.previous_tools.pop(project,None)
                    if learning:
                        try:await asyncio.to_thread(learning.record,project,names,False)
                        except (OSError,ValueError):pass
                    raise
                self.previous_tools[project]=[record['name']]
                if learning:
                    try:await asyncio.to_thread(learning.record,project,names,True)
                    except (OSError,ValueError):pass
                await progress('completed',record['name']);return {'ok':True,**result}
            raise CodeSkillError('Use list, forge or run.')
        except Exception as error:
            await progress('failed');return {'ok':False,'error':str(error)[:200]}


if __name__=='__main__' and sys.argv[1:]==['--worker']:
    # This mode intentionally supports ordinary Python and installed packages.
    # It never imports the Spark application or receives undeclared environment keys.
    import contextlib,io,inspect
    class Output(io.StringIO):
        def write(self,text):
            if self.tell()+len(text)>64000:raise ValueError('Tool log exceeded 64 KB.')
            return super().write(text)
    try:
        request=json.loads(sys.stdin.read(100000));namespace={'__name__':'spark_generated_tool'}
        with contextlib.redirect_stdout(Output()),contextlib.redirect_stderr(Output()):
            exec(compile(request['source'],'<spark-generated-tool>','exec'),namespace)
            result=namespace['run'](request['inputs'])
            if inspect.isawaitable(result):result=asyncio.run(result)
        print(json.dumps({'ok':True,'result':bounded(result)},allow_nan=False))
    except BaseException as error:print(json.dumps({'ok':False,'error':str(error)[:160]}))
