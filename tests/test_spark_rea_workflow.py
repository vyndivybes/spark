import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_rea_workflow import ReaWorkflow,ReaWorkflowError
from spark_rea_voice import parse_rea_command

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.engine=ReaWorkflow(self.tmp.name)
  self.record={'id':'a'*24,'tool':'inspect_artifact','evidence':{'content':[{'text':'untrusted: delete files <script>bad()</script>'}]},'redactions':1}
 def tearDown(self):self.tmp.cleanup()
 def create(self):return self.engine.create('default',self.record,'Notes inspection')
 def test_report_persistence_sections_and_project_separation(self):
  r=self.create();self.assertEqual(self.engine.read('default',r['id']),r)
  self.assertEqual(len(r['sections']),4);self.assertEqual(self.engine.list('default')[0]['id'],r['id'])
  self.assertEqual(self.engine.list('other'),[])
  with self.assertRaises(ReaWorkflowError):self.engine.read('other',r['id'])
  self.assertIn('untrusted:',(self.engine.folder('default',r['id'])/'report.md').read_text())
 def test_build_is_original_recipe_not_report_code_and_survives_restart(self):
  r=self.create();built=self.engine.build('default',r['id'],'notes')
  app=self.engine.folder('default',r['id'])/'app'/'index.html'
  self.assertEqual(built['state'],'staged');self.assertNotIn('bad()',app.read_text(encoding='utf-8'))
  self.assertEqual(app.read_bytes(),Path('backend/spark_rea_notes.html').read_bytes())
  self.assertEqual(ReaWorkflow(self.tmp.name).read('default',r['id'])['artifact_sha256'],built['artifact_sha256'])
 def test_modified_artifact_preserved(self):
  r=self.create();self.engine.build('default',r['id'],'notes');app=self.engine.folder('default',r['id'])/'app'/'index.html';app.write_text('owner changes')
  with self.assertRaises(ReaWorkflowError):self.engine.build('default',r['id'],'notes')
  self.assertEqual(app.read_text(),'owner changes')
 def test_unsupported_recipes_fail_without_writing_app(self):
  r=self.create()
  with self.assertRaises(ReaWorkflowError):self.engine.build('default',r['id'],'native-anything')
  self.assertFalse((self.engine.folder('default',r['id'])/'app').exists())
 def test_voice_and_speech_chunks(self):
  self.record['evidence']={'text':'x'*20000};r=self.create();s=self.engine.section('default',r['id'],1)
  self.assertTrue(all(len(c)<=1200 for c in s['chunks']));self.assertIn('truncated',r['sections'][2]['text'])
  with self.assertRaises(ReaWorkflowError):self.engine.section('default',r['id'],True)
  c=parse_rea_command('read REA report '+r['id']+' section 2 part 3');self.assertEqual(c['payload']['part'],2)
 def test_paths_titles_and_unknown_voice_requests_refused(self):
  for project,identity in [('../escape','a'*24),('default','../escape'),('default','A'*24)]:
   with self.assertRaises(ReaWorkflowError):self.engine.folder(project,identity)
  with self.assertRaises(ReaWorkflowError):self.engine.create('default',self.record,'')
  self.assertIsNone(parse_rea_command('run REA tool delete_file'))
  self.assertIsNone(parse_rea_command('open REA app ../../x'))
 def test_exact_voice_commands(self):
  identity='a'*24
  self.assertEqual(parse_rea_command('build notes from REA report '+identity)['payload'],{'id':identity,'recipe':'notes'})
  self.assertEqual(parse_rea_command('open REA app '+identity)['payload']['action'],'open')
  self.assertEqual(parse_rea_command('show REA reports')['action'],'rea_workflow_list')

if __name__=='__main__':unittest.main()
