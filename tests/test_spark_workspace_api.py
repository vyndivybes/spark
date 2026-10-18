"""SPARK socket-independent workspace action contract: actual ARKUS engines."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_workspace import SparkWorkspace, WorkspaceError

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=SparkWorkspace(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()

    def test_document_import_search_listing_and_deletion_are_real(self):
        doc=self.store.execute("import_document","carbon",{
            "name":"frame.md","data":b"Composite frame Toray T700S and tensile coupon plan."})
        self.assertEqual(doc["name"],"frame.md")
        self.assertEqual(len(self.store.execute("list_documents","carbon",{})),1)
        results=self.store.execute("search_documents","carbon",{"query":"Toray T700S"})
        self.assertEqual(results[0]["title"],"frame.md")
        self.assertIn("tensile coupon",results[0]["excerpt"])
        self.assertEqual(self.store.execute("search_documents","software",{"query":"Toray"}),[])
        self.store.execute("remove_document","carbon",{"id":doc["id"]})
        self.assertEqual(self.store.execute("list_documents","carbon",{}),[])

    def test_skill_propose_test_activate_run_and_rollback(self):
        base={"name":"faw","description":"Compute laminate resin mass",
              "operation":"multiply","inputs":["area","areal_mass"]}
        draft=self.store.execute("propose_skill","carbon",{"spec":base})
        with self.assertRaises(WorkspaceError):
            self.store.execute("run_skill","carbon",{"name":"faw","params":{"area":4,"areal_mass":150}})
        self.store.execute("test_skill","carbon",{"id":draft["id"]})
        self.store.execute("activate_skill","carbon",{"id":draft["id"]})
        answer=self.store.execute("run_skill","carbon",{"name":"faw","params":{"area":4,"areal_mass":150}})
        self.assertEqual(answer["result"],600)
        revision={**base,"operation":"add","description":"Add",
                  "tests":[{"parameters":{"area":4,"areal_mass":150},"expected":154}]}
        newer=self.store.execute("revise_skill","carbon",{"id":draft["id"],"spec":revision})
        self.store.execute("test_skill","carbon",{"id":newer["id"]})
        self.store.execute("activate_skill","carbon",{"id":newer["id"]})
        self.assertEqual(self.store.execute("run_skill","carbon",{"name":"faw","params":{"area":4,"areal_mass":150}})["result"],154)
        self.store.execute("rollback_skill","carbon",{"id":newer["id"]})
        self.assertEqual(self.store.execute("run_skill","carbon",{"name":"faw","params":{"area":4,"areal_mass":150}})["result"],600)

    def test_rejects_unsanctioned_code_bogus_projects_and_extra_payload(self):
        for action,project,data in [
            ("run_shell","carbon",{"cmd":"calc"}),
            ("list_documents","../private",{}),
            ("import_document","carbon",{"name":"hack.py","data":b"print(1)"}),
            ("list_documents","carbon",{"api_key":"not permitted"}),
            ("propose_skill","carbon",{"spec":{"name":"shell","description":"bad","operation":"exec","inputs":["command"]}}),
        ]:
            with self.subTest(action=action,project=project),self.assertRaises(WorkspaceError):
                self.store.execute(action,project,data)
        self.assertEqual(self.store.execute("list_documents","carbon",{}),[])
        self.assertEqual(self.store.execute("list_skills","carbon",{}),[])

    def test_import_cannot_index_non_bytes_or_oversized_content(self):
        for invalid in (None,"not bytes",b"X"*2_000_001):
            with self.assertRaises(WorkspaceError):
                self.store.execute("import_document","carbon",{"name":"safe.txt","data":invalid})

if __name__=="__main__":
    unittest.main()
