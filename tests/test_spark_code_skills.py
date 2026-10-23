"""Behavioral coverage for persistent generated code skills and REA provenance."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_code_skills import CodeSkills,CodeSkillError,execute,parse_source
from spark_evolution import Evolution
from spark_workspace import SparkWorkspace
from spark_maintenance import MaintenanceError


def spec(source='def run(inputs):\n    return sum([item["score"] * item["weight"] for item in inputs])'):
    return {'name':'weighted_score','description':'Weighted score from rows','source':source,
      'tests':[{'inputs':[{'score':4,'weight':0.5},{'score':8,'weight':0.5}],'expected':6}, {'inputs':[],'expected':0}]}


class CodeSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.skills=CodeSkills(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_real_worker_and_lifecycle_persist_without_restart(self):
        first=self.skills.propose('default',spec())
        with self.assertRaises(CodeSkillError):self.skills.action('default','run',first['id'],inputs=[])
        self.assertEqual(self.skills.action('default','test',first['id'])['status'],'tested')
        with self.assertRaises(CodeSkillError):self.skills.action('default','activate',first['id'])
        self.skills.action('default','activate',first['id'],approved=True)
        reloaded=CodeSkills(self.root)
        self.assertEqual(reloaded.action('default','run',first['id'],inputs=[{'score':3,'weight':2}])['result'],6)
        wrong=self.skills.propose('default',spec('def run(inputs):\n    return 99'))
        self.assertEqual(self.skills.action('default','test',wrong['id'])['status'],'rejected')
        with self.assertRaises(CodeSkillError):self.skills.action('default','activate',wrong['id'],approved=True)
        self.assertEqual(reloaded.action('default','run',first['id'],inputs=[])['result'],0)
        self.skills.action('default','deactivate',first['id'])
        with self.assertRaises(CodeSkillError):reloaded.action('default','run',first['id'],inputs=[])
        self.assertEqual(reloaded.list('other'),[])
    def test_no_python_execution_or_private_introspection(self):
        for source in ['import os','def run(inputs):\n return open("secret")',
                       'def run(inputs):\n return inputs.__class__',
                       'def run(inputs):\n return __import__("os")',
                       'def run(inputs):\n return 2**1000000000',
                       'def run(inputs):\n return run(inputs)']:
            with self.subTest(source=source),self.assertRaises(CodeSkillError):parse_source(source)
        with self.assertRaises(CodeSkillError):execute('def run(inputs):\n return "x" * inputs',1000000000)
    def test_local_statements_generators_and_step_limit(self):
        source='def run(inputs):\n    values = [x for x in inputs if x > 0]\n    if len(values) == 0:\n        return 0\n    return sum(x for x in values)'
        self.assertEqual(execute(source,[-2,3,4]),7)
        self.assertEqual(execute(source,[]),0)
        with self.assertRaises(CodeSkillError):
            execute('def run(inputs):\n    return [x for x in inputs for y in inputs]',list(range(150)))

    def test_project_traversal_and_revision_integrity(self):
        with self.assertRaises(CodeSkillError):self.skills.list('../escape')
        candidate=self.skills.propose('default',spec())
        self.skills.action('default','test',candidate['id'])
        second=self.skills.propose('default',spec())
        self.skills.action('default','test',second['id'])
        self.skills.action('default','activate',candidate['id'],approved=True)
        self.skills.action('default','activate',second['id'],approved=True)
        self.assertEqual(len([r for r in self.skills.list('default') if r['status']=='active']),1)
        # Restore an older tested revision by reviewing and retesting it.
        self.skills.action('default','test',candidate['id'])
        self.skills.action('default','activate',candidate['id'],approved=True)
        self.assertEqual(self.skills.action('default','run',candidate['id'],inputs=[])['result'],0)


class EvolutionCodeSkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_rea_evidence_test_activate_run(self):
        with tempfile.TemporaryDirectory() as folder:
            rea=AsyncMock();rea.request.return_value={'content':[{'type':'text','text':'{"finding":"weighted rows"}'}]}
            generator=AsyncMock(return_value=spec())
            evolution=Evolution(SparkWorkspace(folder),generator=generator,rea=rea)
            evidence=await evolution.execute('capture_rea_evidence','default',{'name':'inspect_artifact','arguments':{'path':'sample'}})
            record=await evolution.execute('generate_code_skill','default',{'description':'Compute weighted scores from engineering rows','analysis_id':None,'rea_evidence_id':evidence['id']})
            self.assertEqual(record['provenance']['rea_tool'],'inspect_artifact')
            rea.request.return_value={'password':'sensitive-value','finding':'safe inventory'}
            redacted=await evolution.execute('capture_rea_evidence','default',{'name':'inspect_artifact','arguments':{'path':'sample'}})
            self.assertEqual(redacted['evidence']['password'],'[redacted]')
            self.assertEqual(redacted['evidence']['finding'],'safe inventory')
            self.assertGreater(redacted['redactions'],0)
            self.assertIn('rea_evidence_excerpt',generator.call_args.args[1])
            await evolution.execute('test_code_skill','default',{'id':record['id']})
            await evolution.execute('activate_code_skill','default',{'id':record['id'],'approved':True})
            result=await evolution.execute('run_code_skill','default',{'id':record['id'],'inputs':[]})
            self.assertEqual(result['result'],0)
            with self.assertRaises(MaintenanceError):
                await evolution.execute('generate_code_skill','default',{'description':'Compute weighted rows','analysis_id':None,'rea_evidence_id':'../escape'})
