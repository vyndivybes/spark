import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from spark_intelligence.semantic import SemanticIndex


class SemanticTests(unittest.TestCase):
    def test_local_vector_ranking_preserves_sources_without_keyword_match(self):
        vectors={'automobile':[1.,0.],'car maintenance':[1.,0.],'orchid care':[0.,1.]}
        def encode(texts):return [vectors[text] for text in texts]
        index=SemanticIndex(encoder=encode)
        result=index.search('automobile',[{'id':'a','body':'car maintenance','source':'document:a'}, {'id':'b','body':'orchid care','source':'document:b'}])
        self.assertTrue(result['available'])
        self.assertEqual(result['results'][0]['id'],'a')
        self.assertEqual(result['results'][0]['source'],'document:a')

    def test_missing_local_model_falls_back_without_download_or_importing_torch(self):
        result=SemanticIndex(model_path='C:/does-not-exist/spark-model').search('hello',[{'id':'a','body':'hello'}])
        self.assertFalse(result['available'])
        self.assertEqual(result['results'],[])

    def test_invalid_vector_dimensions_fail_closed(self):
        result=SemanticIndex(encoder=lambda texts:[[1],[1,2]]).search('query',[{'id':'a','body':'text'}])
        self.assertFalse(result['available'])
