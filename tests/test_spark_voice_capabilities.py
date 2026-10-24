"""Governed voice surface for OpenJarvis capabilities 01-16.

The Capabilities Center pages drive every backend action with explicit
owner controls in the UI; by *voice* only read-only status, history and
bounded local research phrasings are governed in. This suite proves:
mutation phrasings never parse, allowed phrasings map exactly to real
ACTION_KEYS actions, and every allowed action speaks an honest summary
from live workbench results. No network, no cloud.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError
import spark_workbench_voice as voice


class GovernanceTests(unittest.TestCase):
    def test_allowed_intents_cover_the_sixteen_capability_status_actions(self):
        expected = {
            "digest_status", "digest_run", "digest_history", "digest_speech", "hub_status",
            "proactive_summary", "proactive_inbox", "opencode_status",
            "research_run", "trace_status", "learning_status",
            "spec_search_status",
            "skill_status", "skill_list", "agents_status", "monitor_status",
            "connector_status", "eval_status", "eval_history",
            "telemetry_status", "telemetry_report", "backend_describe",
        }
        self.assertEqual(voice.CAPABILITY_VOICE_ACTIONS, expected)

    def test_every_governed_action_is_a_real_workbench_action(self):
        for action in voice.CAPABILITY_VOICE_ACTIONS:
            self.assertIn(action, ACTION_KEYS)

    def test_allowed_phrasings_parse_with_exact_payloads(self):
        cases = [
            ("show the morning digest status", "digest_status", {}),
            ("run the morning digest now", "digest_run", {}),
            ("prepare morning digest", "digest_run", {}),
            ("show me the digest history", "digest_history", {"limit": 5}),
            ("check the messaging hub status", "hub_status", {}),
            ("show the proactive daily summary", "proactive_summary", {}),
            ("list the proactive inbox", "proactive_inbox",
             {"state": "", "limit": 20}),
            ("check the opencode status", "opencode_status", {}),
            ("research what documents mention carbon",
             "research_run", {"question": "what documents mention carbon",
                              "max_hops": ""}),
            ("run deep research about vault notes",
             "research_run", {"question": "vault notes", "max_hops": ""}),
            ("check the trace learning status", "trace_status", {}),
            ("check the learning status", "learning_status", {}),
            ("check the spec search status", "spec_search_status", {}),
            ("check the skill ecosystem status", "skill_status", {}),
            ("show the skill list", "skill_list", {}),
            ("check the agent runtime status", "agents_status", {}),
            ("check the monitor status", "monitor_status", {}),
            ("check the connector status", "connector_status", {}),
            ("check the evaluation status", "eval_status", {}),
            ("show the evaluation history", "eval_history", {"limit": 5}),
            ("check the telemetry status", "telemetry_status", {}),
            ("read the telemetry report for groq", "telemetry_report",
             {"model": "groq"}),
            ("show the inference backend status", "backend_describe", {}),
        ]
        for utterance, action, payload in cases:
            command = voice.parse_workbench_command(utterance)
            self.assertIsNotNone(command, utterance)
            self.assertEqual(command["action"], action, utterance)
            self.assertEqual(command["payload"], payload, utterance)

    def test_mutation_phrasings_never_reach_the_dispatcher(self):
        refused = [
            "approve the whatsapp message",
            "send the approved whatsapp message",
            "disconnect the whatsapp channel",
            "configure the messaging hub",
            "approve the proposal",
            "execute the approved proposal",
            "revoke the connector",
            "activate the learning policy",
            "roll back the learning policy",
            "activate the spec candidate",
            "revoke the skill",
            "record a telemetry measurement",
            "capture a trace",
            "run a headless opencode session",
            "capture the git patch",
            "run the monitor now",
            "cancel the monitor",
            "acknowledge the events",
            "select the routed model",
            "opt in the vllm engine",
            "generate with the ollama engine",
            "probe the ollama engine",
            "export the evaluation report",
            "register the candidate",
        ]
        for utterance in refused:
            command = voice.parse_workbench_command(utterance)
            self.assertTrue(
                command is None or command["action"] not in voice.CAPABILITY_VOICE_ACTIONS,
                f"mutating phrasing reached the dispatcher: {utterance!r}")

    def test_voice_allowlist_gates_every_legacy_intent_too(self):
        self.assertIn("save_preference", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertIn("add_agenda", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertIn("workbench_snapshot", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertIn("agent_snapshot", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertIn("intelligence_health", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertNotIn("proactive_execute", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertNotIn("hub_send", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertNotIn("backend_opt_in", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertNotIn("connector_revoke", voice.VOICE_WORKBENCH_ACTIONS)
        self.assertNotIn("opencode_run", voice.VOICE_WORKBENCH_ACTIONS)

    def test_unknown_actions_are_not_governed_by_voice(self):
        for action in ("hub_send", "proactive_execute", "opencode_run",
                       "connector_revoke", "backend_opt_in",
                       "learning_activate", "skill_run", "trace_capture"):
            self.assertNotIn(action, voice.VOICE_WORKBENCH_ACTIONS)


class VoiceLoopAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    """Full honest loop: voice command -> workbench dispatch -> spoken text."""

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.directory.name)
        self.workbench = Workbench(self.workspace)
        self.addAsyncCleanup(self._close)

    async def _close(self):
        await self.workbench.integrations.close()
        await self.workbench.intelligence.close()
        self.directory.cleanup()

    async def test_every_governed_action_executes_and_speaks_honestly(self):
        for action in sorted(voice.CAPABILITY_VOICE_ACTIONS):
            payload = dict(next(p["payload"] for p in [
                voice.parse_workbench_command(utterance)
                for utterance in self._utterances(action)]
                if p is not None and p["action"] == action))
            if action == 'digest_speech':
                with self.assertRaises(WorkbenchError):
                    await self.workbench.execute(action, 'general', payload)
                continue  # No completed digest exists; narration must refuse.
            result = await self.workbench.execute(action, "general", payload)
            spoken = voice.capability_voice_summary(action, result)
            self.assertTrue(isinstance(spoken, str) and spoken.strip(),
                            f"no honest spoken text for {action}: {result!r}")
            lowered = spoken.lower()
            for fake_claim in ("configured and verified",
                               "all engines online"):
                # The spoken summary may never invent readiness.
                self.assertNotIn(fake_claim, lowered)

    @staticmethod
    def _utterances(action):
        table = {
            "digest_status": ["show the morning digest status"],
            "digest_speech": ["play morning digest"],
            "digest_run": ["run the morning digest now"],
            "digest_history": ["show me the digest history"],
            "hub_status": ["check the messaging hub status"],
            "proactive_summary": ["show the proactive daily summary"],
            "proactive_inbox": ["list the proactive inbox"],
            "opencode_status": ["check the opencode status"],
            "research_run": ["research what documents mention carbon"],
            "trace_status": ["check the trace learning status"],
            "learning_status": ["check the learning status"],
            "spec_search_status": ["check the spec search status"],
            "skill_status": ["check the skill ecosystem status"],
            "skill_list": ["show the skill list"],
            "agents_status": ["check the agent runtime status"],
            "monitor_status": ["check the monitor status"],
            "connector_status": ["check the connector status"],
            "eval_status": ["check the evaluation status"],
            "eval_history": ["show the evaluation history"],
            "telemetry_status": ["check the telemetry status"],
            "telemetry_report": ["read the telemetry report for groq"],
            "backend_describe": ["show the inference backend status"],
        }
        return table[action]

    async def test_honest_failure_is_spoken_not_swallowed(self):
        with self.assertRaises(WorkbenchError) as caught:
            await self.workbench.execute("telemetry_capture", "general",
                                         {"model": "groq", "prompt": "ping",
                                          "allow_cloud": False})
        self.assertIn("consent", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
