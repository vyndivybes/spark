"""Real Python import/API workers, dynamic registration and provider gateways."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_python_tools import PythonTools,GeneratedToolGateway,generated_live_config,GATEWAY_NAME
from spark_code_skills import CodeSkillError
from spark_evolution import Evolution
from spark_workspace import SparkWorkspace
from spark_groq import GroqClient,read_http_body,GroqUnavailable


def tool(source='import math\ndef run(inputs):\n    return math.factorial(inputs["n"])'):
 return {'name':'factorial_tool','description':'Factorial with input n','source':source,'requirements':[],'environment':[],
         'tests':[{'inputs':{'n':0},'expected':1},{'inputs':{'n':5},'expected':120}]}

class PythonWorkerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.tools=PythonTools(self.temp.name);self.tools.configure(True,True)
 def tearDown(self):self.temp.cleanup()
 def activate(self,spec):
  row=self.tools.propose('default',spec)
  self.assertEqual(self.tools.action('default','test',row['id'],approved=True)['status'],'tested')
  return self.tools.action('default','activate',row['id'],approved=True)
 def test_imports_expected_results_persistence_and_stop(self):
  row=self.activate(tool());self.assertEqual(self.tools.action('default','run',row['id'],inputs={'n':6})['result'],720)
  reloaded=PythonTools(self.temp.name);self.assertEqual(reloaded.list('default')[0]['status'],'active')
  wrong=tool('def run(inputs):\n return 42');candidate=self.tools.propose('default',wrong)
  self.assertEqual(self.tools.action('default','test',candidate['id'],approved=True)['status'],'rejected')
  with self.assertRaises(CodeSkillError):self.tools.action('default','activate',candidate['id'],approved=True)
  self.tools.configure(False,False)
  with self.assertRaises(CodeSkillError):reloaded.action('default','run',row['id'],inputs={'n':0})
 def test_actual_http_api_access_from_active_worker(self):
  class Handler(BaseHTTPRequestHandler):
   def do_GET(self):
    data=b'{"value": 17}';self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
   def log_message(self,*args):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   source='import json\nimport urllib.request\ndef run(inputs):\n    if "fixture" in inputs: return inputs["fixture"]["value"]\n    with urllib.request.urlopen(inputs["url"], timeout=3) as response: return json.load(response)["value"]'
   spec={'name':'api_value','description':'Read JSON value via HTTP','source':source,'requirements':[],'environment':[],
     'tests':[{'inputs':{'fixture':{'value':1}},'expected':1},{'inputs':{'fixture':{'value':0}},'expected':0}]}
   row=self.activate(spec)
   self.assertEqual(self.tools.action('default','run',row['id'],inputs={'url':f'http://127.0.0.1:{server.server_port}/value'})['result'],17)
  finally:server.shutdown();server.server_close()
 def test_disabling_terminates_owned_running_worker(self):
  import time
  spec=tool('import time\ndef run(inputs):\n    if inputs.get("slow"): time.sleep(20)\n    return inputs.get("n",0)')
  spec['tests']=[{'inputs':{'n':1},'expected':1},{'inputs':{'n':2},'expected':2}]
  row=self.activate(spec);errors=[]
  def run():
   try:self.tools.action('default','run',row['id'],inputs={'slow':True})
   except CodeSkillError as error:errors.append(str(error))
  thread=threading.Thread(target=run);thread.start()
  for _ in range(100):
   with self.tools.worker_lock:running=bool(self.tools.workers)
   if running:break
   time.sleep(.01)
  self.assertTrue(running)
  self.tools.configure(False,False);thread.join(5)
  self.assertFalse(thread.is_alive());self.assertTrue(errors)

 def test_review_before_code_execution_and_declared_environment(self):
  row=self.tools.propose('default',tool())
  with self.assertRaises(CodeSkillError):self.tools.action('default','test',row['id'])
  spec={'name':'env_probe','description':'Probe only synthetic declared environment','source':'import os\ndef run(inputs):\n return {"declared": os.environ.get("SPARK_TOOL_CANARY"), "undeclared": os.environ.get("SPARK_OTHER_CANARY")}','requirements':[],'environment':['SPARK_TOOL_CANARY'],
    'tests':[{'inputs':{},'expected':{'declared':'synthetic','undeclared':None}},{'inputs':{'other':1},'expected':{'declared':'synthetic','undeclared':None}}]}
  with patch.dict(os.environ,{'SPARK_TOOL_CANARY':'synthetic','SPARK_OTHER_CANARY':'must-not-transfer'}):self.activate(spec)

class GatewayTests(unittest.IsolatedAsyncioTestCase):
 async def test_invent_test_register_run_without_restart_and_progress(self):
  with tempfile.TemporaryDirectory() as folder:
   evolution=Evolution(SparkWorkspace(folder),generator=AsyncMock(return_value=tool()))
   evolution.python_tools.configure(True,True);events=[]
   async def emit(event):events.append(event['phase'])
   gateway=GeneratedToolGateway(evolution,'default',emit)
   self.assertEqual((await gateway.call({'action':'list'}))['tools'],[])
   forged=await gateway.call({'action':'forge','goal':'Create a factorial tool using math imports'})
   self.assertEqual(forged['status'],'active')
   result=await gateway.call({'action':'run','name':'factorial_tool','input_json':'{"n":6}'})
   self.assertEqual(result['result'],720)
   self.assertEqual(events,['generating','testing','registered','running','completed'])
   gateway.authorized=lambda:False
   self.assertFalse((await gateway.call({'action':'run','name':'factorial_tool'}))['ok'])
 async def test_one_automatic_source_repair_preserves_expected_tests(self):
  with tempfile.TemporaryDirectory() as folder:
   bad=tool('def run(inputs):\n return 42')
   generator=AsyncMock(side_effect=[bad,{'source':'import math\ndef run(inputs):\n return math.factorial(inputs["n"])'}])
   evolution=Evolution(SparkWorkspace(folder),generator=generator)
   evolution.python_tools.configure(True,True);gateway=GeneratedToolGateway(evolution,'default')
   forged=await gateway.call({'action':'forge','goal':'Invent factorial using math'})
   self.assertEqual(forged['status'],'active')
   records=evolution.python_tools.list('default')
   self.assertEqual(records[0]['status'],'rejected')
   self.assertEqual(records[1]['tests'],bad['tests'])
   self.assertEqual(generator.await_count,2)

 async def test_fragmented_provider_json_is_read_to_eof(self):
  class Content:
   def __init__(self):self.parts=[b'{"tool_',b'calls":',b'[]}',b'']
   async def read(self,n):return self.parts.pop(0)
  self.assertEqual(json.loads(await read_http_body(Content())),{'tool_calls':[]})
  with self.assertRaises(GroqUnavailable):await read_http_body(Content(),limit=5)

 async def test_groq_model_tool_call_reaches_real_registry(self):
  with tempfile.TemporaryDirectory() as folder:
   evolution=Evolution(SparkWorkspace(folder));evolution.python_tools.configure(True,True)
   row=evolution.python_tools.propose('default',tool());evolution.python_tools.action('default','test',row['id'],approved=True);evolution.python_tools.action('default','activate',row['id'],approved=True)
   gateway=GeneratedToolGateway(evolution,'default');api=GroqClient(key='test-only')
   api._http=AsyncMock(side_effect=[{'choices':[{'message':{'content':None,'tool_calls':[{'id':'call1','type':'function','function':{'name':GATEWAY_NAME,'arguments':'{"action":"run","name":"factorial_tool","input_json":"{\\"n\\":6}"}'}}]}}]}, {'choices':[{'message':{'content':'Result is 720.'}}]}])
   answer=await api.chat_generated('Run factorial of six',[],gateway,lambda:False)
   self.assertEqual(answer,'Result is 720.')
   body=api._http.call_args_list[1].kwargs['body'];self.assertIn('720',body['messages'][-1]['content'])
   config=generated_live_config({'system_instruction':'No tools are provided in cinematic voice mode.'},gateway)
   self.assertEqual(config['tools'][0]['function_declarations'][0]['name'],GATEWAY_NAME)
   self.assertNotIn('No tools are provided',config['system_instruction'])
