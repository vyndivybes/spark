import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_intelligence.memory import Memory, reciprocal_rank_fusion


class MemoryTests(unittest.TestCase):
    def test_arkus_chunk_configuration_is_bounded_and_affects_real_import(self):
        from arkus_knowledge_base import KnowledgeBase,KnowledgeError
        with tempfile.TemporaryDirectory() as directory:
            knowledge=KnowledgeBase(directory,chunk_size=300,chunk_overlap=30)
            result=knowledge.import_bytes('general','notes.md',('Detailed engineering notes. '*60).encode())
            self.assertGreater(result['chunks'],3)
            self.assertTrue(knowledge.search('general','engineering'))
            with self.assertRaises(KnowledgeError):KnowledgeBase(directory,chunk_size=0,chunk_overlap=30)

    def test_project_isolation_deduplication_expiration_and_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[1000]
            memory=Memory(directory,clock=lambda:now[0])
            first=memory.remember('general','session','Use metric units','user',ttl=10)
            duplicate=memory.remember('general','session','Use metric units','user',ttl=10)
            self.assertEqual(first['id'],duplicate['id'])
            self.assertEqual(memory.search('private','metric')['results'],[])
            result=memory.search('general','metric',semantic=True)
            self.assertEqual(result['mode'],'fts5')
            self.assertEqual(result['results'][0]['source'],'user')
            now[0]=1011
            self.assertEqual(memory.search('general','metric')['results'],[])
            item=memory.remember('general','task','Verified area is twelve','job:123')
            memory.delete('general',item['id'])
            self.assertEqual(memory.search('general','area')['results'],[])
            memory.close()

    def test_fusion_preserves_citation_and_combines_duplicate_ranks(self):
        result=reciprocal_rank_fusion([[{'id':'a','source':'document:1'},{'id':'b'}],[{'id':'b'},{'id':'c'}]])
        self.assertEqual(result[0]['id'],'b')
        self.assertEqual(next(x for x in result if x['id']=='a')['source'],'document:1')

    def test_invalid_scope_and_limits_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            memory=Memory(directory)
            for project,body,ttl in [('../bad','hello',10),('general','x'*10001,10),('general','hello',-1)]:
                with self.assertRaises(ValueError):memory.remember(project,'task',body,'user',ttl=ttl)
            memory.close()
