"""Groq-only cloud voice fallback: no Ollama, no silent Gemini paid model."""
import asyncio
import io
import struct
import sys
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_groq import (
    cloud_provider, GroqVoiceLoop, GroqUnavailable, pcm_to_wav,
    wav_to_pcm24k, tts_text, groq_model
)
from spark_public_apis import registry, public_api_answer

def chunk(value):
    return struct.pack("<1600h", *([value]*1600))

class CloudModeTests(unittest.IsolatedAsyncioTestCase):
    def test_no_ollama_dependency_and_explicit_groq(self):
        with patch.dict("os.environ",{},clear=True):
            self.assertEqual(cloud_provider(),"gemini")
        with patch.dict("os.environ",{"SPARK_AI_PROVIDER":"groq"},clear=True):
            self.assertEqual(cloud_provider(),"groq")
        with patch.dict("os.environ",{"SPARK_AI_PROVIDER":"ollama"},clear=True):
            self.assertEqual(cloud_provider(),"gemini")
        with patch.dict("os.environ",{"SPARK_GROQ_MODEL":"arbitrary-paid"},clear=True):
            self.assertEqual(groq_model(),"llama-3.1-8b-instant")

    def test_wav_is_valid_16khz_and_tts_normalizes_to_24k_pcm(self):
        result=pcm_to_wav(chunk(4000)*5)
        with wave.open(io.BytesIO(result),"rb") as reader:
            self.assertEqual(reader.getframerate(),16000)
            self.assertEqual(reader.getnchannels(),1)
            self.assertEqual(reader.getnframes(),8000)
        result24=wav_to_pcm24k(result)
        self.assertAlmostEqual(len(result24),24000,delta=4)
        self.assertEqual(len(result24)%2,0)

    def test_tts_input_is_bounded_at_groq_200_character_limit(self):
        self.assertTrue(len(tts_text("An answer. "*150))<=190)
        self.assertTrue(tts_text("Hello").startswith("[professionally]"))

    async def test_voice_vad_triggers_single_request_and_returns_pcm(self):
        calls=[]
        answers=[]
        sounds=[]
        class Fake:
            async def transcribe(self,wav):
                calls.append("stt")
                return "Hello SPARK"
            async def chat(self,text,history):
                calls.append("chat")
                return "Hello sir."
            async def speak(self,text):
                calls.append("tts")
                return pcm_to_wav(chunk(3500)*3)
        loop=GroqVoiceLoop(api=Fake(),on_transcription=lambda d:answers.append(d),
                           on_browser_audio=lambda b:sounds.append(b),
                           audio_playback_wait=False)
        loop.set_paused(False)
        for _ in range(5):
            await loop.process_pcm(chunk(7000))
        for _ in range(9):
            await loop.process_pcm(chunk(0))
        self.assertEqual(calls,["stt","chat","tts"])
        self.assertEqual(len(sounds),1)
        self.assertEqual(answers[0],{"sender":"User","text":"Hello SPARK"})
        self.assertEqual(answers[-1],{"sender":"ADA","text":"Hello sir."})
        for _ in range(12):
            await loop.process_pcm(chunk(0))
        self.assertEqual(calls.count("stt"),1)

    async def test_vad_ignores_noise_and_mute(self):
        class Never:
            async def transcribe(self,wav):
                raise AssertionError("unexpected audio upload")
        loop=GroqVoiceLoop(api=Never(),audio_playback_wait=False)
        for _ in range(30):
            await loop.process_pcm(chunk(250))
        loop.set_paused(False)
        for _ in range(40):
            await loop.process_pcm(chunk(250))
        for _ in range(5):
            await loop.process_pcm(chunk(7000))
        loop.set_paused(True)
        for _ in range(15):
            await loop.process_pcm(chunk(0))
        self.assertEqual(loop.recorded_chunks,0)

    async def test_provider_error_is_redacted_and_does_not_fallback(self):
        failures=[]
        class Quota:
            async def transcribe(self,wav):
                raise GroqUnavailable("Groq free-tier rate limit reached (429).")
        loop=GroqVoiceLoop(api=Quota(),on_error=failures.append,audio_playback_wait=False)
        loop.set_paused(False)
        for _ in range(4):
            await loop.process_pcm(chunk(6500))
        for _ in range(9):
            await loop.process_pcm(chunk(0))
        self.assertEqual(len(failures),1)
        self.assertIn("429",failures[0])

    async def test_public_apis_are_fixed_host_https_and_no_weather_commercial_use(self):
        ids=[x["id"] for x in registry()]
        self.assertEqual(ids,["wikipedia","frankfurter"])
        self.assertTrue(all(x["url"].startswith("https://") for x in registry()))
        got=[]
        async def request(url):
            got.append(url)
            if "frankfurter" in url:
                return {"date":"2026-10-16","base":"USD","quote":"INR","rate":89.25}
            return {"title":"Bicycle","extract":"A human powered machine."}
        result=await public_api_answer("convert 12 usd to inr",request)
        self.assertIn("1071",result["text"])
        self.assertEqual(got[0],"https://api.frankfurter.dev/v2/rate/usd/inr")
        result2=await public_api_answer("wiki Bicycle",request)
        self.assertIn("human powered",result2["text"])
        self.assertEqual(result2["sources"][0]["url"],"https://en.wikipedia.org/wiki/Bicycle")
        self.assertIsNone(await public_api_answer("fetch https://127.0.0.1",request))
        self.assertEqual(len(got),2)

if __name__=="__main__":
    unittest.main()
