# Ported actual ARKUS behavior contract (user-owned source), imports point to SPARK backend.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
"""Tests of offline project-isolated knowledge ingestion and search."""
import base64
import io
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from knowledge_base import KnowledgeBase, KnowledgeError

class KnowledgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.store=KnowledgeBase(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_import_search_persistence_and_dedup(self):
  d=self.store.import_bytes("general","layup.md",b"# Composite Material\nT700S prototype layup has 0.224 mm nominal ply. Engineering only.")
  self.assertEqual(d["chunks"],1)
  self.assertEqual(len(self.store.search("general","T700S prototype")),1)
  self.assertEqual(self.store.import_bytes("general","layup.md",b"# Composite Material\nT700S prototype layup has 0.224 mm nominal ply.")["replaced"],True)
  self.assertEqual(len(self.store.list("general")),1)
  self.assertEqual(KnowledgeBase(self.tmp.name).search("other","T700S"),[])
  self.assertEqual(len(KnowledgeBase(self.tmp.name).search("general","T700S")),1)
 def test_docx_parse_and_blocks_macros(self):
  buf=io.BytesIO()
  with zipfile.ZipFile(buf,"w") as z:
   z.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Carbon design requirement</w:t></w:r></w:p></w:body></w:document>')
  self.store.import_bytes("general","spec.docx",buf.getvalue())
  self.assertEqual(len(self.store.search("general","Carbon")),1)
  with self.assertRaises(KnowledgeError):self.store.import_bytes("general","macro.docm",buf.getvalue())
 def test_size_and_traversal_checks(self):
  for name in ("../secret.md","secret.exe","a/b.md",""):
   with self.assertRaises(KnowledgeError):self.store.import_bytes("general",name,b"hello")
  with self.assertRaises(KnowledgeError):self.store.import_bytes("../secret","x.txt",b"valid")
  with self.assertRaises(KnowledgeError):self.store.import_bytes("general","a.txt",b"x"*2_100_000)
  with self.assertRaises(KnowledgeError):self.store.import_bytes("general","empty.txt",b"")
 def test_remove_and_fts_tokenization(self):
  doc=self.store.import_bytes("general","memo.txt",b"Calibration certification procedures for endurance bicycle frames")
  self.assertEqual(len(self.store.search("general","certification")),1)
  self.store.remove("general",doc["id"])
  self.assertEqual(self.store.search("general","certification"),[])
 def test_offline_pdf_explicit_when_extractor_unavailable(self):
  with self.assertRaises(KnowledgeError):
   self.store.import_bytes("general","scan.pdf",b"not a PDF")
