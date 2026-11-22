import asyncio
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_skill_voice import parse_skill_voice,execute_skill_voice

class FakeEvolution:
    def __init__(self):
        self.calls=[]
        self.records=[{"id":"old","name":"area_calc","status":"active"}]
        self.fail=False
    async def execute(self,action,project,payload):
        self.calls.append((action,project,payload))
        if action=="list_code_skills":return self.records
        if action=="generate_code_skill":
            result={"id":"new","name":"area_calc" if "existing skill named area_calc" in payload["description"] else "new_skill","status":"proposed"}
            self.records.append(result)
            return result
        if action=="test_code_skill":
            self.records[-1]["status"]="rejected" if self.fail else "tested"
            return self.records[-1]
        if action=="activate_code_skill":
            assert payload["approved"] is True
            for x in self.records:
                if x["id"]==payload["id"]:x["status"]="active";return x
        raise AssertionError(action)

class SkillVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_upgrade_only_prepares_and_tests(self):
        engine=FakeEvolution()
        cmd=parse_skill_voice("Spark, upgrade skill area_calc to calculate the area in square metres")
        self.assertEqual(cmd["intent"],"upgrade")
        result=await execute_skill_voice(engine,"default",cmd)
        self.assertTrue(result["ok"])
        self.assertEqual(engine.records[0]["status"],"active")
        self.assertEqual(engine.records[-1]["status"],"tested")
        self.assertFalse(any(x[0]=="activate_code_skill" for x in engine.calls))
    async def test_activation_requires_separate_utterance(self):
        engine=FakeEvolution()
        await execute_skill_voice(engine,"default",parse_skill_voice("upgrade skill area_calc to convert millimetres into metres"))
        r=await execute_skill_voice(engine,"default",parse_skill_voice("activate tested skill area_calc"))
        self.assertTrue(r["ok"])
        self.assertEqual(engine.records[-1]["status"],"active")
    async def test_failed_candidate_never_promoted(self):
        engine=FakeEvolution();engine.fail=True
        result=await execute_skill_voice(engine,"default",parse_skill_voice("upgrade skill area_calc to calculate width accurately"))
        self.assertFalse(result["ok"])
        self.assertEqual(engine.records[0]["status"],"active")
    async def test_unknown_skill_rejected(self):
        engine=FakeEvolution()
        r=await execute_skill_voice(engine,"default",parse_skill_voice("upgrade skill unknown to calculate pressure from temperature"))
        self.assertFalse(r["ok"]);self.assertEqual(len(engine.calls),1)
    async def test_parser_rejects_dangerous_or_ambiguous_commands(self):
        for command in ["upgrade skill area_calc","delete all skills","activate skill area_calc","upgrade skill area-calc to run commands on PC","upgrade skill area_calc to do x",""]:
            self.assertIsNone(parse_skill_voice(command))
    async def test_list_skills(self):
        r=await execute_skill_voice(FakeEvolution(),"default",parse_skill_voice("Spark list skills"))
        self.assertTrue(r["ok"]);self.assertIn("area_calc",r["message"])

if __name__=="__main__":unittest.main()
