# Ported actual ARKUS behavior contract (user-owned source), imports point to SPARK backend.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import tempfile
import unittest
from arkus_skill_forge import SkillForge, SkillError

class SkillUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.forge=SkillForge(self.directory.name)
        self.base={'name':'calc','description':'Sum','operation':'add','inputs':['a','b']}
        first=self.forge.propose(self.base,'general');self.forge.test('general',first['id']);self.forge.activate('general',first['id']);self.first=first['id']
    def tearDown(self):self.directory.cleanup()
    def spec(self,expected=12):
        return {**self.base,'description':'Product','operation':'multiply','tests':[{'parameters':{'a':3,'b':4},'expected':expected}]}
    def test_bad_expected_output_blocks_upgrade_and_preserves_active_skill(self):
        candidate=self.forge.revise('general',self.first,self.spec(expected=99))
        with self.assertRaises(SkillError):self.forge.test('general',candidate['id'])
        with self.assertRaises(SkillError):self.forge.activate('general',candidate['id'])
        self.assertEqual(self.forge.run('general','calc',{'a':3,'b':4})['result'],7)
    def test_tested_upgrade_is_atomic_persistent_and_can_roll_back(self):
        candidate=self.forge.revise('general',self.first,self.spec())
        self.assertEqual(self.forge.run('general','calc',{'a':3,'b':4})['result'],7)
        self.forge.test('general',candidate['id']);self.forge.activate('general',candidate['id'])
        restored=SkillForge(self.directory.name)
        self.assertEqual(restored.run('general','calc',{'a':3,'b':4})['result'],12)
        restored.rollback('general',candidate['id'])
        self.assertEqual(restored.run('general','calc',{'a':3,'b':4})['result'],7)
        self.assertEqual(sum(x['status']=='active' for x in restored.available('general')),1)
    def test_upgrade_requires_independent_examples_and_retains_interface(self):
        for spec in [self.base,{**self.spec(),'inputs':['x','y']},{**self.spec(),'name':'other'}]:
            with self.assertRaises(SkillError):self.forge.revise('general',self.first,spec)
    def test_stale_competing_revision_cannot_replace_the_new_active_version(self):
        one=self.forge.revise('general',self.first,self.spec());two=self.forge.revise('general',self.first,self.spec())
        self.forge.test('general',one['id']);self.forge.test('general',two['id']);self.forge.activate('general',one['id'])
        with self.assertRaises(SkillError):self.forge.activate('general',two['id'])
        with self.assertRaises(SkillError):self.forge.activate('general',self.first)
    def test_acceptance_cases_validate_numeric_results_without_running_code(self):
        for cases in [[{'parameters':{'a':3,'b':4},'expected':True}], [{'parameters':{'a':3},'expected':3}]]:
            with self.assertRaises(SkillError):self.forge.propose({**self.base,'name':'new_skill','tests':cases},'general')

    def test_unsupported_code_and_nonfinite_expected_results_are_rejected(self):
        for spec in [{**self.spec(),"code":"print('unsafe')"}, {**self.spec(),"tests":[{"parameters":{"a":3,"b":4},"expected":float("inf")}]},
                     {**self.spec(),"tests":[{"parameters":{"a":10**1000,"b":4},"expected":0}]}]:
            with self.assertRaises(SkillError):self.forge.revise('general',self.first,spec)
