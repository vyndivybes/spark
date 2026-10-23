"""Durable recall through real JSONL/SQLite and provider request boundaries."""
import json
import ast
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from project_manager import ProjectManager
from spark_conversation_memory import conversation_live_config, RECALL_TOOL, REMEMBER_TOOL, bounded_messages, prime_conversation
from spark_groq import GroqVoiceLoop, GroqUnavailable, GroqClient
from spark_live_profile import select_live_config


class ConversationMemoryTests(unittest.TestCase):
    def test_explicit_personal_details_have_no_expiry_and_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            result = pm.remember_detail("user-name", "Test User")
            self.assertTrue(result["saved"])
            self.assertIsNone(result["expires"])
            restarted = ProjectManager(folder)
            self.assertEqual(restarted.get_remembered_details()["user-name"], "Test User")
            restarted.remember_detail("user-name", "Corrected Name")
            self.assertEqual(ProjectManager(folder).get_remembered_details(), {"user-name": "Corrected Name"})
            with self.assertRaises(ValueError):
                restarted.remember_detail("../name", "invalid")

    def test_people_incidents_and_discussions_survive_restart_and_recent_window(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Ananya is my sister. We discussed her Pune studio opening after the flood.")
            pm.log_chat("SPARK", "We can plan the studio opening.")
            for n in range(140):
                pm.log_chat("User", f"Unrelated daily update {n}")
            restarted = ProjectManager(folder)
            self.assertNotIn("Ananya", restarted.format_recent_chat_context())
            for query in ("Who is Ananya?", "What happened during the flood?", "What did we discuss about the studio?"):
                context = restarted.format_memory_context(query)
                self.assertIn("Ananya is my sister", context)
                self.assertIn('"speaker": "User"', context)
                self.assertIn('"source": "chat:temp:', context)
                self.assertIn("studio opening", context)

    def test_incremental_import_includes_corrections_without_duplicate_records(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Ananya lives in Pune.")
            first = pm.format_memory_context("Ananya")
            self.assertEqual(first, pm.format_memory_context("Ananya"))
            pm.log_chat("User", "Correction: Ananya moved to Kochi.")
            context = pm.format_memory_context("Ananya")
            self.assertEqual(context.count('"text": "Ananya lives in Pune."'), 1)
            self.assertIn("Ananya moved to Kochi", context)
            self.assertLess(context.index("Pune"), context.index("Kochi"))

    def test_project_isolation_empty_and_fts_special_characters(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Ananya is my sister.")
            pm.create_project("Private")
            pm.switch_project("Private")
            self.assertEqual(pm.format_memory_context("Ananya"), "")
            pm.switch_project("temp")
            self.assertIn("Ananya", pm.format_memory_context('Ananya " OR * - ('))
            for query in ("", "?!", None, "what did we discuss"):
                self.assertEqual(pm.format_memory_context(query), "")
            self.assertEqual(pm.format_memory_context("nonexistentword"), "")

    def test_legacy_bad_records_partial_append_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            log = pm.get_current_project_path() / "chat_history.jsonl"
            log.write_text('invalid\n[]\n' + json.dumps({"sender": "User", "text": "Ananya had a bicycle incident."}) + '\n', encoding="utf-8")
            self.assertIn("bicycle incident", pm.format_memory_context("Ananya"))
            with log.open("a", encoding="utf-8") as stream:
                stream.write('{"sender":"User","text":"Ananya recovered"')
            self.assertNotIn("recovered", pm.format_memory_context("Ananya"))
            with log.open("a", encoding="utf-8") as stream:
                stream.write('}\n')
            self.assertIn("recovered", pm.format_memory_context("Ananya"))
            log.write_text(json.dumps({"sender": "User", "text": "Ananya is well"}) + '\n', encoding="utf-8")
            result = pm.format_memory_context("Ananya")
            self.assertIn("Ananya is well", result)
            self.assertNotIn("bicycle", result)

    def test_live_config_enables_transcripts_and_read_only_recall(self):
        for profile in ("cinematic", "cinematic_tools", "full"):
            original = select_live_config(profile, {"response_modalities": ["AUDIO"]})
            result = conversation_live_config(original, profile)
            declarations = [d for tool in result["tools"] for d in tool.get("function_declarations", [])]
            self.assertIn(RECALL_TOOL, [d["name"] for d in declarations])
            self.assertEqual(result["input_audio_transcription"], {})
            self.assertEqual(result["output_audio_transcription"], {})
            self.assertNotIn("input_audio_transcription", original)
        minimal = {"response_modalities": ["AUDIO"]}
        self.assertIs(conversation_live_config(minimal, "voice"), minimal)

    def test_long_exchange_retrieves_the_matching_passage_with_bounded_context(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Unrelated background. " * 300 + "Ananya had a bicycle incident and recovered.")
            context = pm.format_memory_context("Ananya")
            self.assertIn("bicycle incident and recovered", context)
            self.assertLess(len(context), 7500)

    def test_structured_dialogue_preserves_multiline_messages_and_role_text(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            text = "Ananya said:\nSPARK: this is quoted text, still part of my message."
            pm.log_chat("User", text)
            pm.log_chat("SPARK", "Understood.")
            self.assertEqual(ProjectManager(folder).get_conversation_messages(), [
                {"role": "user", "content": text}, {"role": "assistant", "content": "Understood."}])

    def test_context_budget_keeps_latest_exchange_and_complete_log(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Earlier details. " * 3000)
            pm.log_chat("SPARK", "What is the final decision?")
            pm.log_chat("User", "Meet Ananya on Friday.")
            context = pm.get_conversation_messages()
            self.assertEqual(context[-1]["content"], "Meet Ananya on Friday.")
            self.assertLessEqual(sum(len(m["content"]) for m in context), 24000)
            self.assertEqual(len(pm.get_recent_chat_history()[0]["text"]), len("Earlier details. " * 3000))


class GroqMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_permanent_name_request_saves_and_recalls_without_generic_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            outputs = []
            loop = GroqVoiceLoop(api=object(), project_manager=ProjectManager(folder), on_transcription=outputs.append)
            await loop.handle_text("Can you remember my name permanently?")
            self.assertIn("What is your name?", outputs[-1]["text"])
            self.assertEqual(loop.project_manager.get_remembered_details(), {})
            await loop.handle_text("My name is Test User.")
            self.assertIn("Saved your name as Test User", outputs[-1]["text"])
            restarted = GroqVoiceLoop(api=object(), project_manager=ProjectManager(folder), on_transcription=outputs.append)
            await restarted.handle_text("Can you remember my name permanently?")
            self.assertIn("Test User", outputs[-1]["text"])
            self.assertIn("across restarts", outputs[-1]["text"])

    async def test_cloud_request_retains_dialogue_beyond_the_old_six_message_window(self):
        requests = []
        class CaptureClient(GroqClient):
            async def _http(self, url, **kwargs):
                requests.append(kwargs["body"])
                return {"choices": [{"message": {"content": "We can continue."}}]}
        history = [{"role": "user", "content": "The studio budget is 45000 rupees."}]
        history += [{"role": "assistant" if n % 2 else "user", "content": f"Planning detail {n}"} for n in range(12)]
        prompt = "More details. " * 120 + "Final decision: Friday."
        await CaptureClient(key="test-only").chat(prompt, history)
        messages = requests[0]["messages"]
        self.assertTrue(any("45000 rupees" in message["content"] for message in messages))
        self.assertTrue(messages[-1]["content"].endswith("Final decision: Friday."))

    async def test_continue_after_restart_carries_the_conversation_without_topic_keywords(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "We are planning Ananya's studio opening. The budget is 45000 rupees.")
            pm.log_chat("SPARK", "We still need to decide on the venue and invitations.")
            for n in range(5):
                pm.log_chat("User", f"Planning detail {n}")
                pm.log_chat("SPARK", f"Noted detail {n}")
            requests = []
            class FakeCloud:
                async def chat(self, prompt, history):
                    requests.append(history)
                    return "We were planning the studio opening."
            loop = GroqVoiceLoop(api=FakeCloud(), project_manager=ProjectManager(folder))
            await loop.handle_text("Continue where we left off")
            context = "\n".join(message["content"] for message in requests[0])
            self.assertIn("45000 rupees", context)
            self.assertIn("venue and invitations", context)

    async def test_long_conversation_message_is_saved_without_losing_its_ending(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            class FakeCloud:
                async def chat(self, prompt, history):
                    return "Recorded."
            loop = GroqVoiceLoop(api=FakeCloud(), project_manager=pm)
            text = "The discussion covered several details. " * 60 + "Final decision: meet Ananya on Friday."
            await loop.handle_text(text)
            self.assertEqual(pm.get_recent_chat_history(2)[0]["text"], text)

    async def test_real_saved_history_reaches_cloud_request_and_new_turns_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Ananya is my sister and her studio flooded.")
            for n in range(20):
                pm.log_chat("User", f"daily update {n}")
            requests = []
            class FakeCloud:
                async def chat(self, prompt, history):
                    requests.append((prompt, history))
                    return "You told me Ananya is your sister."
            loop = GroqVoiceLoop(api=FakeCloud(), project_manager=ProjectManager(folder))
            await loop.handle_text("Who is Ananya?")
            self.assertTrue(any("Ananya is my sister" in message["content"] for message in requests[0][1]))
            self.assertEqual(requests[0][1][-1]["role"], "system")
            saved = ProjectManager(folder).get_recent_chat_history(2)
            self.assertEqual([(e["sender"], e["text"]) for e in saved], [
                ("User", "Who is Ananya?"), ("SPARK", "You told me Ananya is your sister.")])
            self.assertFalse(any(e["role"] == "system" for e in loop._history))

    async def test_user_turn_is_retained_when_provider_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            class FailedCloud:
                async def chat(self, prompt, history):
                    raise GroqUnavailable("Unavailable")
            loop = GroqVoiceLoop(api=FailedCloud(), project_manager=ProjectManager(folder))
            await loop.handle_text("Ananya called about the incident.")
            self.assertEqual(ProjectManager(folder).get_recent_chat_history()[-1]["text"], "Ananya called about the incident.")

    async def test_voice_turns_are_saved_and_local_document_excerpts_stay_local(self):
        with tempfile.TemporaryDirectory() as folder:
            class FakeCloud:
                async def transcribe(self, wav):
                    return "Ananya called about the incident."
                async def chat(self, prompt, history):
                    return "I will remember that conversation."
            pm = ProjectManager(folder)
            loop = GroqVoiceLoop(api=FakeCloud(), project_manager=pm)
            await loop.handle_audio(b"fake audio at provider boundary")
            self.assertEqual([e["sender"] for e in pm.get_recent_chat_history()], ["User", "SPARK"])
            async def search(query):
                return [{"title": "Private doc", "excerpt": "LocalOnlySecret"}]
            loop.on_workspace_search = search
            await loop.handle_text("search my knowledge for confidential")
            self.assertNotIn("LocalOnlySecret", (pm.get_current_project_path() / "chat_history.jsonl").read_text())


class GeminiMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_recall_tool_returns_old_conversation_evidence(self):
        # Execute the real streaming handler against the provider boundary,
        # without opening hardware or an authenticated cloud connection.
        source = Path(__file__).resolve().parents[1] / "backend" / "spark.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        audio = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AudioLoop")
        method = next(node for node in audio.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "receive_audio")
        scope = {"asyncio": asyncio, "RECALL_TOOL": RECALL_TOOL, "REMEMBER_TOOL": REMEMBER_TOOL,
                 "types": SimpleNamespace(FunctionResponse=SimpleNamespace), "live_profile": lambda: "cinematic"}
        from spark_web import WEB_NAMES
        scope["WEB_NAMES"] = WEB_NAMES
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), scope)
        responses = []
        class Session:
            async def receive(self):
                yield SimpleNamespace(data=None, server_content=None,
                                      tool_call=SimpleNamespace(function_calls=[SimpleNamespace(
                                          name=RECALL_TOOL, args={"query": "Ananya"}, id="recall-1")]))
                raise asyncio.CancelledError()
            async def send_tool_response(self, function_responses):
                responses.extend(function_responses)
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Ananya is my sister. Her studio flooded.")
            from unittest.mock import Mock
            loop = SimpleNamespace(session=Session(), project_manager=pm, flush_chat=Mock())
            with self.assertRaises(asyncio.CancelledError):
                await scope["receive_audio"](loop)
            self.assertEqual(responses[0].id, "recall-1")
            self.assertIn("Her studio flooded", responses[0].response["result"])
            loop.flush_chat.assert_called_once()

    async def test_every_gemini_connection_restores_dialogue_silently(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = ProjectManager(folder)
            pm.log_chat("User", "Ananya's studio budget is 45000 rupees.")
            pm.log_chat("SPARK", "The venue is still undecided.")
            from unittest.mock import AsyncMock
            session = SimpleNamespace(send_client_content=AsyncMock())
            for _ in range(2):
                await prime_conversation(session, ProjectManager(folder))
            self.assertEqual(session.send_client_content.await_count, 2)
            for call in session.send_client_content.await_args_list:
                self.assertFalse(call.kwargs["turn_complete"])
                context = call.kwargs["turns"]["parts"][0]["text"]
                self.assertIn("45000 rupees", context)
                self.assertIn("venue is still undecided", context)


if __name__ == "__main__":
    unittest.main()
