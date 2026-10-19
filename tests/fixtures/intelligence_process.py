"""Disposable subprocess harness. All writes stay in its explicitly supplied test directory."""
import asyncio
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from spark_intelligence.runtime import Runtime,PolicyError
from spark_cinematic_tools import get_system_status


async def main(directory,phase):
    directory=Path(directory)
    effects=directory/'test-effects.json'
    def count():return json.loads(effects.read_text()) if effects.exists() else 0
    async def execute(action,args,project):
        if phase=='crash':os._exit(17)
        value=get_system_status()
        effects.write_text(json.dumps(count()+1))
        return {'ok':value.get('service')=='SPARK Core','value':value}
    runtime=Runtime(directory,executor=execute,clock=lambda:1000 if phase in ('schedule','checkpoint','crash') else 1002)
    try:
        plan=[{'action':'get_system_status','args':{},'depends':[]}]
        if phase in ('schedule','checkpoint','crash'):
            if phase=='checkpoint':plan.append({'action':'get_system_status','args':{},'depends':[0]})
            job=runtime.create('test','Process acceptance',plan)
            runtime.authorize('test',job['id'],job['plan_hash'],approved=True)
            if phase=='schedule':
                runtime.schedule('test',job['id'],{'kind':'once','at':1001},approved=True)
                runtime.configure_scheduler(True,approved=True)
            else:job=await runtime.run('test',job['id'],max_steps=1)
            result={'effects':count(),'cursor':job['cursor']}
        elif phase=='tick':
            results=await runtime.tick()
            result={'runs':len(results),'effects':count()}
        elif phase=='resume':
            job=await runtime.run('test',runtime.jobs('test')[0]['id'])
            result={'effects':count(),'cursor':job['cursor'],'state':job['state']}
        elif phase=='inspect':
            job=runtime.jobs('test')[0]
            denied=False
            try:await runtime.run('test',job['id'])
            except PolicyError:denied=True
            result={'state':job['state'],'execution_denied':denied}
        elif phase=='without-packages':
            from spark_workspace import SparkWorkspace
            from spark_workbench import Workbench
            workbench=Workbench(SparkWorkspace(directory))
            try:
                job=await workbench.execute('agent_create','test',{'title':'No optional packages','plan':plan})
                await workbench.execute('agent_authorize','test',{'id':job['id'],'plan_hash':job['plan_hash'],'approved':True})
                completed=await workbench.execute('agent_run','test',{'id':job['id']})
                memory=await workbench.execute('memory_search','test',{'query':'hello','semantic':True})
                result={'state':completed['state'],'memory_mode':memory['mode'],'optional_modules_loaded':any(name in sys.modules for name in ('httpx','mcp','torch','dspy','gepa','faiss','sentence_transformers'))}
            finally:
                await workbench.intelligence.close()
                await workbench.integrations.close()
        else:raise ValueError('Unknown test phase')
        print(json.dumps(result))
    finally:await runtime.close()


if __name__=='__main__':asyncio.run(main(*sys.argv[1:]))
