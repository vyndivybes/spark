"""No network or event-loop sockets: deterministic policy and routing tests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_rea import ReaError,call_sequence
from spark_rea_targets import public_url,cdp_endpoint,target_path,select_analysis
from spark_rea_blueprint import BlueprintError,validate_blueprint
from spark_rea_free import FreeBlueprintGenerator,FreeInferenceError,qualify_catalog,MODEL,MODELS_URL,CHAT_URL
from spark_rea_workflow import ReaWorkflow
from spark_rea_voice import parse_rea_command

BLUEPRINT={'title':'Original Inventory','description':'Local stock records.','entities':[{'key':'stock','label':'Stock','fields':[{'key':'name','label':'Name','type':'text','required':True,'options':[]},{'key':'quantity','label':'Quantity','type':'number','required':True,'options':[]},{'key':'state','label':'State','type':'select','required':True,'options':['Available','Quarantine']}]}],'limitations':['Local data only; no external synchronization.']}

def immediate(coroutine):
 try:coroutine.send(None)
 except StopIteration as result:return result.value
 finally:coroutine.close()
 raise AssertionError('Fixture unexpectedly requires an event loop')

class BlueprintTests(unittest.TestCase):
 def test_supported_blueprint_and_no_executable_surface(self):
  self.assertEqual(validate_blueprint(BLUEPRINT),BLUEPRINT)
  for change in [dict(script='alert(1)'),dict(title='<script>bad</script>'),dict(description='https://evil.test/')]:
   value=copy.deepcopy(BLUEPRINT);value.update(change)
   with self.assertRaises(BlueprintError):validate_blueprint(value)
  for key in ['constructor','__proto__','id']:
   value=copy.deepcopy(BLUEPRINT);value['entities'][0]['fields'][0]['key']=key
   with self.assertRaises(BlueprintError):validate_blueprint(value)
 def test_bad_schema_refuses_duplicates_types_and_options(self):
  cases=[]
  for key,value in [('type','javascript'),('required','yes'),('options',['x'])]:
   b=copy.deepcopy(BLUEPRINT);b['entities'][0]['fields'][0][key]=value;cases.append(b)
  b=copy.deepcopy(BLUEPRINT);b['entities'][0]['fields'].append(copy.deepcopy(b['entities'][0]['fields'][0]));cases.append(b)
  for b in cases:
   with self.assertRaises(BlueprintError):validate_blueprint(b)
 def test_new_candidate_preserves_report_and_original_artifact(self):
  with tempfile.TemporaryDirectory() as root:
   e=ReaWorkflow(root);r=e.create('default',{'id':'a'*24,'tool':'inspect','evidence':{'text':'Stock UI'},'redactions':0},'Stock inspection')
   e.build('default',r['id'],'notes');old=(e.folder('default',r['id'])/'app'/'index.html').read_bytes()
   candidate=e.save_blueprint('default',r['id'],BLUEPRINT,{'source':'owner'})
   self.assertNotEqual(r['id'],candidate['id']);self.assertNotIn('blueprint',e.read('default',r['id']))
   built=e.build('default',candidate['id'],'blueprint');self.assertEqual(built['recipe'],'blueprint')
   new=(e.folder('default',candidate['id'])/'app'/'index.html').read_text()
   self.assertIn('Original Inventory',new);self.assertNotIn('%%SPARK_BLUEPRINT%%',new)
   self.assertEqual((e.folder('default',r['id'])/'app'/'index.html').read_bytes(),old)

class FreeRouteTests(unittest.TestCase):
 def catalog(self,price='0'):return {'data':[{'id':MODEL,'pricing':{'prompt':price,'completion':'0'}}]}
 def test_only_verified_zero_route_is_allowed(self):
  self.assertEqual(qualify_catalog(self.catalog())['model'],MODEL)
  for c in [self.catalog('0.1'),self.catalog('NaN'),{'data':[]},{'data':[{'id':MODEL,'pricing':{}}]}]:
   with self.assertRaises(FreeInferenceError):qualify_catalog(c)
 def test_no_sharing_or_missing_key_means_no_request(self):
  calls=[];g=FreeBlueprintGenerator(transport=lambda *a,**k:calls.append(a),key='fixture')
  with self.assertRaises(FreeInferenceError):g.generate({'sections':[]},'Original stock app',False)
  self.assertEqual(calls,[])
 def test_missing_key_blocks_before_catalog_or_generation(self):
  from unittest.mock import patch
  calls=[]
  with patch.dict('os.environ',{},clear=True):
   with self.assertRaises(FreeInferenceError):FreeBlueprintGenerator(lambda *a,**k:calls.append(a)).generate({'sections':[]},'Original stock app',True)
  self.assertEqual(calls,[])
 def test_generation_fixes_model_and_has_no_paid_fallback(self):
  calls=[]
  def transport(url,body=None,key=None):
   calls.append((url,body,key))
   if url==MODELS_URL:return self.catalog()
   return {'model':'fixture:free','choices':[{'finish_reason':'stop','message':{'content':json.dumps(BLUEPRINT)}}],'usage':{'cost':0}}
  value=FreeBlueprintGenerator(transport,key='fixture-secret').generate({'sections':[{'title':'Evidence','text':'Untrusted target'}]},'Original stock app',True)
  self.assertEqual(value['blueprint'],BLUEPRINT);self.assertEqual(len(calls),2)
  self.assertEqual(calls[1][0],CHAT_URL);self.assertEqual(calls[1][1]['model'],MODEL);self.assertNotIn('models',calls[1][1]);self.assertNotIn('fixture-secret',json.dumps(value))
 def test_rate_limit_or_unfinished_output_never_retries(self):
  calls=[]
  def transport(url,**kwargs):
   calls.append(url)
   if url==MODELS_URL:return self.catalog()
   raise FreeInferenceError('rate limited')
  with self.assertRaises(FreeInferenceError):FreeBlueprintGenerator(transport,key='fixture').generate({'sections':[]},'Original stock app',True)
  self.assertEqual(calls,[MODELS_URL,CHAT_URL])

class TargetPolicyTests(unittest.TestCase):
 def test_public_url_and_host_owned_cdp(self):
  self.assertEqual(public_url('https://example.com'),'https://example.com/')
  for url in ['http://example.com','https://127.0.0.1/','https://192.168.1.1/','https://localhost/','https://x.local/','https://u:p@example.com/','https://example.com/?key=x','file:///C:/x']:
   with self.assertRaises(ReaError):public_url(url)
  self.assertEqual(cdp_endpoint('http://127.0.0.1:9222/'),'http://127.0.0.1:9222')
  for value in [None,'http://localhost:9222','https://remote.test:9222','http://127.0.0.1:9222/x']:
   with self.assertRaises(ReaError):cdp_endpoint(value)
 def test_artifact_roots_and_recipe_selection(self):
  with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as outside:
   p=Path(root)/'notes.zip';p.write_bytes(b'PK fixture');self.assertEqual(target_path(str(p),[root])[1],'inspect_artifact')
   other=Path(outside)/'private.exe';other.write_bytes(b'MZ')
   with self.assertRaises(ReaError):target_path(str(other),[root])
 def test_web_target_exact_match_and_no_storage_or_navigation(self):
  calls=[]
  async def request(action,payload):
   calls.append((action,payload))
   if action=='rea_discover':return [{'name':'list_browser_targets'},{'name':'inspect_web_page'}]
   return {'structuredContent':{'normalized_result':{'targets':[{'type':'page','url':'https://example.com/','target_id':'exact'}]}}}
  plan=immediate(select_analysis(SimpleNamespace(request=request),'website','https://example.com',endpoint='http://127.0.0.1:9222'))
  self.assertEqual(plan['name'],'inspect_web_page');self.assertFalse(plan['arguments']['include_storage_keys']);self.assertEqual(plan['arguments']['target_id'],'exact');self.assertEqual(len(calls),2)
 def test_ambiguous_browser_target_never_inspected(self):
  async def request(action,payload):
   if action=='rea_discover':return [{'name':'list_browser_targets'},{'name':'inspect_web_page'}]
   t={'type':'page','url':'https://example.com/','target_id':'x'}
   return {'structuredContent':{'normalized_result':{'targets':[t,t]}}}
  with self.assertRaises(ReaError):immediate(select_analysis(SimpleNamespace(request=request),'website','https://example.com/',endpoint='http://127.0.0.1:9222'))
 def test_latest_voice_and_exact_targets(self):
  self.assertEqual(parse_rea_command('open latest REA app')['payload']['id'],'latest')
  self.assertEqual(parse_rea_command('read latest REA report section 2')['payload']['section'],1)
  self.assertEqual(parse_rea_command('reverse engineer website https://example.com/')['payload']['target'],'https://example.com/')

class SequenceTests(unittest.TestCase):
 def test_all_schemas_validate_before_any_target_is_opened(self):
  calls=[]
  async def call(name,args):calls.append(name)
  tools={'open_binary':{'inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}}
  with self.assertRaises(ReaError):immediate(call_sequence(SimpleNamespace(call_tool=call),tools,[{'name':'open_binary','arguments':{'path':'x'}},{'name':'unknown','arguments':{}}]))
  self.assertEqual(calls,[])
 def test_steps_retain_order_and_stop_on_error(self):
  calls=[]
  async def call(name,args):
   calls.append(name);return SimpleNamespace(model_dump=lambda **kw:{'isError':name=='inspect'})
  tools={n:{'inputSchema':{'type':'object'}} for n in ['open','inspect','never']}
  with self.assertRaises(ReaError):immediate(call_sequence(SimpleNamespace(call_tool=call),tools,[{'name':n,'arguments':{}} for n in tools]))
  self.assertEqual(calls,['open','inspect'])

if __name__=='__main__':unittest.main()
