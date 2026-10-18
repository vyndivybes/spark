"""Voice retrieval from real offline ARKUS knowledge must not send document text to Groq."""
import asyncio
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_workspace_voice import knowledge_search_query
from spark_groq import GroqVoiceLoop

class WorkspaceVoiceTests(unittest.IsolatedAsyncioTestCase):
    def test_narrow_local_only_search_intent(self):
        self.assertEqual(knowledge_search_query("search my knowledge for carbon layup"),"carbon layup")
        self.assertEqual(knowledge_search_query("SPARK, find my notes about T700S"),"T700S")
        self.assertIsNone(knowledge_search_query("read password file"))
        self.assertIsNone(knowledge_search_query("search the web for stock price"))
        self.assertIsNone(knowledge_search_query("search my knowledge for T700S then open cmd"))

    async def test_groq_voice_queries_local_knowledge_without_any_cloud_calls(self):
        messages=[]
        queries=[]
        class Never:
            async def chat(self,*args): raise AssertionError("No cloud model is needed for local document search.")
        async def lookup(query):
            queries.append(query)
            return [{"title":"layup.md","excerpt":"Toray T700S cured ply thickness 0.224 mm."}]
        loop=GroqVoiceLoop(api=Never(),on_workspace_search=lookup,
                           on_transcription=messages.append,audio_playback_wait=False)
        await loop.handle_text("search my knowledge for T700S")
        self.assertEqual(queries,["T700S"])
        self.assertIn("layup.md",messages[-1]["text"])
        self.assertIn("0.224",messages[-1]["text"])

    async def test_empty_knowledge_result_stays_offline(self):
        messages=[]
        async def lookup(q):return []
        loop=GroqVoiceLoop(api=object(),on_workspace_search=lookup,
                           on_transcription=messages.append,audio_playback_wait=False)
        await loop.handle_text("search my knowledge for unpublished plans")
        self.assertIn("No local documents matched",messages[-1]["text"])

if __name__=="__main__":
    unittest.main()
