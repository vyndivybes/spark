"""Groq text is audible without a cloud TTS request, greeting costs zero API calls."""
import asyncio
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_groq import GroqVoiceLoop

class VoiceAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_sends_local_speech_and_waits_for_completion(self):
        calls=[]
        announcements=[]
        class Fake:
            async def chat(self,text,history):
                calls.append("chat")
                return "I hear you, sir."
            async def speak(self,text):
                raise AssertionError("Do not call Groq TTS in browser speech mode")
        loop=GroqVoiceLoop(api=Fake(),on_browser_tts=lambda p:announcements.append(p),
                           audio_playback_wait=False)
        loop.browser_ready=True
        loop.set_paused(False)
        task=asyncio.create_task(loop.handle_text("Can you hear me?"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(calls,["chat"])
        self.assertEqual(announcements[0]["text"],"I hear you, sir.")
        self.assertTrue(loop._speaking)
        self.assertFalse(loop.accepting_mic)
        self.assertFalse(task.done())
        loop.browser_speech_done()
        await asyncio.wait_for(task,1)
        self.assertFalse(loop._speaking)
        self.assertTrue(loop.accepting_mic)

    async def test_startup_greeting_once_after_aec_is_ready(self):
        spoken=[]
        class NoApi:
            async def chat(self,*_): raise AssertionError("No chat credit for greeting")
            async def speak(self,*_): raise AssertionError("No TTS credit for greeting")
        loop=GroqVoiceLoop(api=NoApi(),on_browser_tts=spoken.append)
        self.assertFalse(loop.greet_on_ready)
        loop.browser_ready=True
        loop.set_paused(False)
        task=asyncio.create_task(loop.start_greeting())
        await asyncio.sleep(0)
        self.assertEqual(len(spoken),1)
        self.assertIn("SPARK",spoken[0]["text"])
        self.assertIn("sir",spoken[0]["text"].lower())
        self.assertFalse(loop.accepting_mic)
        loop.browser_speech_done()
        await asyncio.wait_for(task,1)
        await loop.start_greeting()
        self.assertEqual(len(spoken),1)
        self.assertTrue(loop.greet_on_ready)

    async def test_browser_speech_failure_ack_unlocks_turn(self):
        notices=[]
        loop=GroqVoiceLoop(api=object(),on_browser_tts=lambda _:None,on_error=notices.append)
        loop.set_paused(False)
        task=asyncio.create_task(loop.start_greeting())
        await asyncio.sleep(0)
        loop.browser_speech_done(error=True)
        await asyncio.wait_for(task,1)
        self.assertTrue(notices)
        self.assertFalse(loop._speaking)

if __name__=="__main__":unittest.main()
