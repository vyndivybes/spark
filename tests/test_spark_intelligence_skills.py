import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_intelligence.skills import InstructionalSkills


class InstructionalSkillTests(unittest.TestCase):
    def test_review_test_activate_and_rollback_preserve_permission_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            skills=InstructionalSkills(directory)
            content='---\nname: summarize-notes\ndescription: Summarize notes with citations\nlicense: Apache-2.0\n---\nCite the supplied source identifiers.'
            first=skills.stage('general',content,'selected SKILL.md')
            with self.assertRaises(ValueError):skills.activate('general',first['id'],approved=True)
            skills.test('general',first['id'])
            skills.activate('general',first['id'],approved=True)
            self.assertEqual(skills.context('general','summarize-notes')['permissions'],[])
            second=skills.stage('general',content+'\nKeep answers brief.','selected revision')
            skills.test('general',second['id'])
            skills.activate('general',second['id'],approved=True)
            skills.rollback('general',second['id'],approved=True)
            self.assertEqual(skills.context('general','summarize-notes')['id'],first['id'])
            with self.assertRaises(ValueError):skills.context('private','summarize-notes')
            skills.close()

    def test_unknown_metadata_and_permission_requests_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            skills=InstructionalSkills(directory)
            for field in ['allowed-tools: shell','name: duplicate','depends: missing']:
                content='---\nname: safe-skill\ndescription: Safe description\n'+field+'\n---\nInstructions'
                with self.assertRaises(ValueError):
                    candidate=skills.stage('general',content,'test');skills.test('general',candidate['id'])
            skills.close()
