"""Integration: actual upstream HOLO notes reader sees explicitly published SPARK FTS5 source."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_workspace import SparkWorkspace
from scripts.holo_notes_launcher import load_vendor, choose_notes_dir

ROOT=Path(__file__).resolve().parents[1]

class HoloBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=SparkWorkspace(self.root)
    def tearDown(self): self.temp.cleanup()

    def test_source_document_requires_explicit_publish_then_is_read_by_real_holo(self):
        doc=self.store.execute("import_document","carbon",{
            "name":"layup.md","data":b"# Layup\nCarbon frame Toray T700S first prototype plan."})
        published=self.store.execute("publish_holo_note","carbon",{"id":doc["id"]})
        self.assertEqual(published["published"],True)
        self.assertEqual(self.store.execute("list_holo_notes","carbon",{})[0]["name"],"layup.md")
        upstream=load_vendor(ROOT/"vendor/holo-gestures"/"server.py",self.store.holo_notes_root)
        tree=upstream.load_tree()
        self.assertTrue(any(x["name"]=="CARBON" for x in tree))
        self.assertIn("T700S",str(tree))
        self.store.execute("unpublish_holo_note","carbon",{"id":doc["id"]})
        self.assertEqual(self.store.execute("list_holo_notes","carbon",{}),[])
        self.assertFalse(any(x["name"]=="CARBON" for x in upstream.load_tree()))

    def test_unpublished_notes_never_appear_in_holo(self):
        self.store.execute("import_document","private",{"name":"confidential.md","data":b"Secret note"})
        self.assertEqual(self.store.execute("list_holo_notes","private",{}),[])
        self.assertEqual(choose_notes_dir(self.root/"missing",ROOT/"vendor/holo-gestures"/"sample-notes"),
                         ROOT/"vendor/holo-gestures"/"sample-notes")

    def test_publishing_rejects_nonexistent_or_unsafe_ids(self):
        for value in ("../escape","not-real","a"*24):
            with self.assertRaises(Exception):
                self.store.execute("publish_holo_note","carbon",{"id":value})

if __name__=="__main__":unittest.main()
