import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_personal_memory import PersonalMemory, MemoryError

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.t=[1000000]
        self.store=PersonalMemory(self.temp.name,clock=lambda:self.t[0])
    def tearDown(self):
        self.temp.cleanup()
    def test_explicit_provenance_and_project_isolation(self):
        m=self.store.remember("personal","Prefer concise spoken answers")
        self.assertEqual(len(self.store.list("personal")),1)
        self.assertEqual(self.store.list("engineering"),[])
        self.assertEqual(self.store.list("personal")[0]["source"],"user_explicit")
        self.assertFalse(self.store.forget("engineering",m["id"])["deleted"])
        self.assertTrue(self.store.forget("personal",m["id"])["deleted"])
    def test_expiration_and_no_implicit_retention(self):
        self.store.remember("personal","Temporary",ttl_days=1)
        self.t[0]+=86400
        self.assertEqual(self.store.list("personal"),[])
    def test_refuse_secrets_and_malformed_values(self):
        for body in ("password: hi","API_KEY = secret","bearer: token", "", "x"*513):
            with self.subTest(body=body[:20]),self.assertRaises(MemoryError):
                self.store.remember("personal",body)
        for project in ("../personal","personal/other","Personal",""):
            with self.subTest(project=project),self.assertRaises(MemoryError):
                self.store.list(project)
        with self.assertRaises(MemoryError):self.store.remember("personal","x",ttl_days=0)
        with self.assertRaises(MemoryError):self.store.remember("personal","x",confidence=2)
    def test_reopen_persists_and_deletion(self):
        identity=self.store.remember("personal","Remember approved project preference")["id"]
        other=PersonalMemory(self.temp.name,clock=lambda:self.t[0])
        self.assertEqual(other.list("personal")[0]["id"],identity)
        self.assertTrue(other.forget("personal",identity)["deleted"])
        self.assertEqual(self.store.list("personal"),[])

if __name__=="__main__":
    unittest.main()
