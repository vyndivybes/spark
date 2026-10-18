"""Stage 9 RED tests: no cloud call and no desktop launch without an explicit user action."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_groq_capabilities import parse_desktop_command, vision_requested, can_groq_vision_frame
from spark_groq import GroqClient, GroqVoiceLoop, GroqUnavailable

JPEG = b"\xff\\xd8\xff" + b"jpeg-data" + b"\xff\\xd9"

class ParsedCommandTests(unittest.TestCase):
    def test_single_whitelisted_desktop_command(self):
        self.assertEqual(parse_desktop_command("SPARK, please open notepad."), "notepad")
        self.assertEqual(parse_desktop_command("Launch calculator"), "calculator")
        self.assertEqual(parse_desktop_command("Can you start Paint?"), "paint")
        for value in ("open browser", "open calc.exe", "open paint and delete my files",
                      "open notepad; shutdown", "open command prompt",
                      "please open https://example.com", "open calculator then run powershell"):
            self.assertIsNone(parse_desktop_command(value))

    def test_only_explicit_vision_questions_trigger_cloud_vision(self):
        for text in ("What do you see?", "describe what you see", "what's in front of the camera?"):
            self.assertTrue(vision_requested(text), text)
        for text in ("Hello", "how is the weather", "open calculator",
                     "what do you see in this code?", "show me your source"):
            self.assertFalse(vision_requested(text), text)

    def test_groq_frame_policy_blocks_other_clients_and_stopped_sessions(self):
        good=dict(provider="groq", owner_sid="owner", sender_sid="owner",
                  sharing_sid="owner", session_ready=True, authenticated=True)
        self.assertTrue(can_groq_vision_frame(**good))
        for field,value in (("provider","gemini"), ("sender_sid","visitor"),
                            ("sharing_sid",None), ("session_ready",False),
                            ("authenticated",False)):
            bad={**good,field:value}
            self.assertFalse(can_groq_vision_frame(**bad), bad)

class GroqVisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_vision_prompt_uses_one_fresh_frame_not_text_chat(self):
        seen=[]
        outputs=[]
        class Fake:
            async def vision(self, prompt, frame):
                seen.append((prompt,frame))
                return "A bicycle on a table."
            async def chat(self,*args):
                raise AssertionError("Vision prompts must not fall back to text")
        loop=GroqVoiceLoop(api=Fake(),on_transcription=outputs.append,audio_playback_wait=False)
        self.assertTrue(loop.set_camera_frame(JPEG,now=time.monotonic()))
        await loop.handle_text("What do you see?")
        self.assertEqual(seen,[("What do you see?",JPEG)])
        self.assertEqual(outputs[-1]["text"],"A bicycle on a table.")

    async def test_stale_or_revoked_camera_never_uploads(self):
        seen=[]
        class Fake:
            async def vision(self,*args):seen.append("vision")
            async def chat(self,*args):return "Normal response."
        loop=GroqVoiceLoop(api=Fake(),audio_playback_wait=False)
        self.assertTrue(loop.set_camera_frame(JPEG,now=time.monotonic()-12))
        await loop.handle_text("What do you see?")
        self.assertEqual(seen,[])
        loop.set_camera_frame(JPEG)
        loop.clear_camera_frame()
        await loop.handle_text("What do you see?")
        self.assertEqual(seen,[])

    async def test_vision_request_uses_fixed_documented_model(self):
        bodies=[]
        client=GroqClient(key="test")
        async def mock_http(url,*,body=None,**kwargs):
            bodies.append((url,body))
            return {"choices":[{"message":{"content":"A chair."}}]}
        client._http=mock_http
        answer=await client.vision("What is this?",JPEG)
        self.assertEqual(answer,"A chair.")
        body=bodies[0][1]
        self.assertEqual(body["model"],"qwen/qwen3.8-27b")
        self.assertEqual(body["messages"][-1]["content"][1]["type"],"image_url")
        self.assertTrue(body["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("GEMINI",str(body))

    async def test_approval_required_for_allowlisted_desktop_command(self):
        asks=[]
        launches=[]
        replies=[]
        async def approve(payload):
            asks.append(payload)
            return True
        def launcher(name):
            launches.append(name)
            return {"ok":True,"message":"Started "+name+"."}
        loop=GroqVoiceLoop(api=object(),on_desktop_approval=approve,launch_app=launcher,
                           on_transcription=replies.append,audio_playback_wait=False)
        await loop.handle_text("open notepad")
        self.assertEqual(launches,["notepad"])
        self.assertEqual(asks,[{"tool":"launch_desktop_app","args":{"app":"notepad"}}])
        self.assertEqual(replies[-1]["text"],"Started notepad.")

    async def test_denied_or_unavailable_approval_never_launches(self):
        launched=[]
        for approver in (None, lambda payload: asyncio.sleep(0,result=False)):
            loop=GroqVoiceLoop(api=object(),on_desktop_approval=approver,
                               launch_app=lambda app:launched.append(app),
                               audio_playback_wait=False)
            await loop.handle_text("open calculator")
        self.assertEqual(launched,[])

if __name__=="__main__":
    unittest.main()
