"""Exercise production routing seams without starting audio/provider engines."""
import ast
import asyncio
import json
from pathlib import Path
import secrets
import sys
import tempfile
from types import SimpleNamespace, MethodType
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_rea_workflow import ReaWorkflow
from spark_maintenance import MaintenanceError,atomic_write,digest

ROOT=Path(__file__).resolve().parents[1]
def function_from_source(file,name,namespace,cls=None):
 tree=ast.parse((ROOT/file).read_text(encoding='utf-8-sig'))
 nodes=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls).body if cls else tree.body
 function=next(n for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
 exec(compile(ast.Module(body=[function],type_ignores=[]),str(file),'exec'),namespace)
 return namespace[name]

def immediate(function):
 """These fake transports complete synchronously; no OS socket/event loop needed."""
 def run(self):
  coroutine=function(self)
  try:
   coroutine.send(None)
  except StopIteration:
   return
  finally:
   coroutine.close()
  raise AssertionError('Fixture unexpectedly needs a live event loop')
 return run

class EvolutionRoutingTests(unittest.TestCase):
 @immediate
 async def test_actual_dispatch_reuses_redaction_and_indexes_only_saved_report(self):
  from spark_rea_workflow import ReaWorkflowError
  from spark_rea_free import FreeInferenceError
  from spark_rea_blueprint import BlueprintError
  tree=ast.parse((ROOT/'backend/spark_evolution.py').read_text(encoding='utf-8-sig'))
  keys=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ACTION_KEYS' for t in n.targets)))
  env=dict(ACTION_KEYS=keys,MaintenanceError=MaintenanceError,ReaWorkflowError=ReaWorkflowError,FreeInferenceError=FreeInferenceError,BlueprintError=BlueprintError,asyncio=asyncio,json=json,secrets=secrets,digest=digest,atomic_write=atomic_write)
  execute=function_from_source('backend/spark_evolution.py','execute',env,'Evolution')
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);indexed=[]
   async def rea_request(action,payload):return {'content':[{'text':'Notes structure'}],'token':'sensitive-value'}
   def workspace_execute(action,project,payload):indexed.append(payload);return {'id':'knowledge-123'}
   owner=SimpleNamespace(lock=asyncio.Lock(),rea_workflows=ReaWorkflow(root),rea=SimpleNamespace(request=rea_request),code_skills=SimpleNamespace(_path=lambda project:root/'code-skills'/'registry.json'),workspace=SimpleNamespace(skills=SimpleNamespace(_file=lambda project:None),execute=workspace_execute))
   owner.execute=MethodType(execute,owner)
   report=await owner.execute('rea_workflow_create','default',{'name':'inspect_artifact','arguments':{},'title':'Notes'})
   self.assertNotIn('sensitive-value',json.dumps(report));self.assertIn('[redacted]',json.dumps(report))
   staged=await owner.execute('rea_workflow_build','default',{'id':report['id'],'recipe':'notes'})
   self.assertEqual(staged['state'],'staged')
   saved=await owner.execute('rea_workflow_index','default',{'id':report['id']})
   self.assertEqual(saved['knowledge_document_id'],'knowledge-123');self.assertIn(b'untrusted source data',indexed[0]['data'])
   spoken=await owner.execute('rea_workflow_speak','default',{'id':report['id'],'section':0,'part':0})
   self.assertLessEqual(len(spoken['text']),400)
   with self.assertRaises(MaintenanceError):await owner.execute('rea_workflow_speak','default',{'id':report['id'],'section':0,'part':99})

 @immediate
 async def test_auto_artifact_dispatch_and_blueprint_build_keep_prior_candidate(self):
  import os
  from unittest.mock import patch
  from spark_rea_targets import select_analysis
  from spark_rea_workflow import ReaWorkflowError
  from spark_rea_blueprint import BlueprintError
  from spark_rea_free import FreeInferenceError
  if __package__:
   from .test_spark_rea_expansion import BLUEPRINT
  else:
   from test_spark_rea_expansion import BLUEPRINT
  tree=ast.parse((ROOT/'backend/spark_evolution.py').read_text(encoding='utf-8-sig'))
  keys=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ACTION_KEYS' for t in n.targets)))
  env=dict(ACTION_KEYS=keys,MaintenanceError=MaintenanceError,ReaWorkflowError=ReaWorkflowError,BlueprintError=BlueprintError,FreeInferenceError=FreeInferenceError,select_analysis=select_analysis,asyncio=asyncio,json=json,secrets=secrets,digest=digest,atomic_write=atomic_write,os=os)
  execute=function_from_source('backend/spark_evolution.py','execute',env,'Evolution')
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'SPARK_REA_ALLOWED_ROOTS':'[]'}):
   root=Path(folder);target=root/'sample.zip';target.write_bytes(b'PK fixture');calls=[]
   async def request(action,payload):
    calls.append(action)
    if action=='rea_discover':return [{'name':'open_binary'},{'name':'inspect_artifact'}]
    return {'content':[{'type':'text','text':'Static package inventory'}]}
   owner=SimpleNamespace(lock=asyncio.Lock(),rea_workflows=ReaWorkflow(root),maintenance=SimpleNamespace(root=root),rea=SimpleNamespace(request=request),code_skills=SimpleNamespace(_path=lambda project:root/'code-skills'/'registry.json'),workspace=SimpleNamespace(skills=SimpleNamespace(_file=lambda project:None)))
   owner.execute=MethodType(execute,owner)
   report=await owner.execute('rea_workflow_analyze','default',{'kind':'artifact','target':str(target)})
   self.assertEqual(calls,['rea_discover','rea_sequence']);self.assertEqual(report['tool'],'rea_sequence')
   candidate=await owner.execute('rea_workflow_blueprint','default',{'id':report['id'],'blueprint':BLUEPRINT})
   app=await owner.execute('rea_workflow_build','default',{'id':candidate['id'],'recipe':'blueprint'})
   self.assertEqual(app['recipe'],'blueprint');self.assertNotEqual(app['id'],report['id'])
   self.assertEqual(owner.rea_workflows.read('default',report['id'])['state'],'reported')

class VoiceRoutingTests(unittest.TestCase):
 @immediate
 async def test_owner_gate_and_exact_utterance_prevent_model_chosen_actions(self):
  env={'audio_loop':None,'SETTINGS':{},'sio':SimpleNamespace(manager=SimpleNamespace(is_connected=lambda *args:True)),'workspace_project_by_sid':{},'re':__import__('re')}
  execute=function_from_source('backend/server.py','voice_workspace_action',env)
  self.assertFalse((await execute('owner','rea_workflow_command',{'command':'show REA reports'},'show REA reports'))['ok'])
  env['audio_loop']=SimpleNamespace(owner_sid='owner',session=object())
  result=await execute('owner','rea_workflow_command',{'command':'build notes from REA report '+'a'*24},'show REA reports')
  self.assertFalse(result['ok'])
  async def rea_result(*args):return 'No saved reports'
  env['rea_voice_result']=rea_result
  self.assertEqual((await execute('owner','rea_workflow_command',{'command':'show REA reports'},'show REA reports'))['text'],'No saved reports')

if __name__=='__main__':unittest.main()
