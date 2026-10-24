"""SPARK conversation-to-tools repair: registration, gate, dispatch and honesty.

Covers the chain the live voice conversation actually uses:
  implementation (spark_insight_tools / spark_autonomous_engine)
  -> registration (MCP_VOICE_TOOLS + AudioLoop methods)
  -> declaration (select_live_config insight toolbox)
  -> gate (allowed_live_tool)
  -> dispatch (AudioLoop.answer_mcp_tool returns real evidence).
Every dispatch test asserts the tool returned a real result AND that results
distinguish unavailable access from not-found source.
"""
import asyncio
import os
import sys
import unittest
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from spark_cinematic_tools import INSIGHT_DECLARATIONS, allowed_live_tool  # noqa: E402
from spark_insight_tools import (  # noqa: E402
    backend_health, git_state, release_summary, search_spark_source)
from spark_live_profile import select_live_config  # noqa: E402


class RegistrationTests(unittest.TestCase):
    """Every declaration must be registered, gated and actually executable."""

    def _dispatchable(self):
        import spark
        return spark.AudioLoop()

    def test_declared_names_are_registered_for_dispatch(self):
        import spark
        for declaration in INSIGHT_DECLARATIONS:
            name = declaration["name"]
            self.assertIn(name, spark.MCP_VOICE_TOOLS,
                          f"{name} declared to Gemini but never registered")
            spec = spark.MCP_VOICE_TOOLS[name]
            self.assertTrue(hasattr(spark.AudioLoop, spec["callback"]),
                            f"{name} dispatch callback {spec['callback']} is not wired")

    def test_registered_callbacks_resolve_on_a_real_loop(self):
        loop = self._dispatchable()
        from spark_cinematic_tools import INSIGHT_TOOL_NAMES
        import spark
        for name in INSIGHT_TOOL_NAMES:
            callback = getattr(loop, spark.MCP_VOICE_TOOLS[name]["callback"], None)
            self.assertIsNotNone(callback, f"{name} would answer 'not configured'")

    def test_cinematic_config_declares_exactly_the_insight_toolbox(self):
        conf = select_live_config("cinematic", {"tools": ["leak"]})
        declared = [tool["name"] for tool in conf["tools"][0]["function_declarations"]]
        self.assertEqual(declared, [tool["name"] for tool in INSIGHT_DECLARATIONS])
        self.assertNotIn("leak", str(conf))

    def test_gate_allows_insight_and_still_closes_actions_in_cinematic(self):
        for declaration in INSIGHT_DECLARATIONS:
            self.assertTrue(allowed_live_tool("cinematic", declaration["name"]))
        for unsafe in ("launch_desktop_app", "write_upgrade_patch", "run_upgrade_tests",
                       "generate_cad", "query_spark_graph", "read_file", "__import__"):
            self.assertFalse(allowed_live_tool("cinematic", unsafe))

    def test_upgrade_mutation_names_stay_refused_on_the_voice_route(self):
        from spark_cinematic_tools import INSIGHT_TOOL_NAMES
        mutated = {"create_upgrade_branch", "write_upgrade_patch", "execute_dev_command",
                   "run_upgrade_tests", "diagnose_and_repair", "verify_upgrade",
                   "stage_upgrade", "rollback_upgrade"}
        self.assertFalse(mutated & INSIGHT_TOOL_NAMES,
                         "Mutation tools must never be declared read-only")


class _AudioLoopCase(unittest.TestCase):
    """Shared real-dispatch helper: one AudioLoop per test method."""

    def _run(self, coro):
        import spark
        if not hasattr(self, "_loop"):
            self._loop = spark.AudioLoop()
        return asyncio.run(coro(self._loop))


class DispatchTests(_AudioLoopCase):
    """Real tool results through the real AudioLoop dispatch path."""

    def test_git_status_returns_actual_head(self):
        # Exercise real git and real dispatch in a throwaway repository. The
        # isolated candidate directory intentionally has no Git metadata.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True,
                                      capture_output=True, text=True, timeout=10).stdout.strip()
            git('init', '-b', 'source-fixture')
            source = root / 'sample.py'
            source.write_text('value = 1\n', encoding='utf-8')
            git('add', 'sample.py')
            git('-c', 'user.name=SPARK Test', '-c', 'user.email=spark-test@localhost',
                '-c', 'core.hooksPath=', 'commit', '--no-gpg-sign', '-m', 'Fixture source')
            expected_head = git('rev-parse', 'HEAD')
            async def call(loop):
                return await loop.answer_mcp_tool('get_spark_git_status', {})
            with patch('spark_insight_tools.PROJECT_ROOT', root):
                report = json.loads(self._run(call))
                self.assertEqual(report['status'], 'ok')
                self.assertEqual(report['head'], expected_head)
                self.assertEqual(report['branch'], 'source-fixture')
                self.assertEqual(report['changed_entries'], 0)
                source.write_text('value = 2\n', encoding='utf-8')
                # A fresh conversation must query Git rather than reuse this
                # conversation's intentional short-lived tool-result cache.
                del self._loop
                changed = json.loads(self._run(call))
                self.assertTrue(changed['dirty'])
                self.assertEqual(changed['changed_entries'], 1)

    def test_non_repository_dispatch_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            async def call(loop):
                return await loop.answer_mcp_tool('get_spark_git_status', {})
            with patch('spark_insight_tools.PROJECT_ROOT', Path(directory)):
                report = json.loads(self._run(call))
            self.assertEqual(report['status'], 'unavailable')

    def test_search_finds_released_block_reason(self):
        async def call(loop):
            return await loop.answer_mcp_tool(
                "search_source_code", {"pattern": r"def block_reason"})

        import json
        report = json.loads(self._run(call))
        self.assertEqual(report["status"], "ok")
        self.assertIn("spark_echo_gate.py", str(report["results"]))

    def test_read_returns_released_source_with_block_reason(self):
        async def call(loop):
            return await loop.answer_mcp_tool(
                "read_source_file", {"file_path": "spark_echo_gate.py"})

        result = self._run(call)
        self.assertIn("def block_reason", result)

    def test_policy_reports_the_disabled_unattended_state(self):
        async def call(loop):
            return await loop.answer_mcp_tool('get_spark_policy', {})
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / 'SPARK/workspace/saee/autonomy-policy.json'
            policy.parent.mkdir(parents=True)
            policy.write_text(json.dumps({'enabled': False, 'allow_model_source': False,
                                          'max_upgrades_per_day': 0}), encoding='utf-8')
            with patch.dict(os.environ, {'LOCALAPPDATA': directory}):
                report = json.loads(self._run(call))
        self.assertEqual(report['status'], 'ok')
        self.assertIs(report['policy']['enabled'], False)
        self.assertEqual(report['policy']['max_upgrades_per_day'], 0)

    def test_release_history_lists_the_accepted_release(self):
        async def call(loop):
            return await loop.answer_mcp_tool('get_spark_release_history', {})
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            release = store / 'releases/fixture'
            release.mkdir(parents=True)
            candidate_hash = 'a' * 64
            (release / 'manifest.json').write_text(json.dumps({
                'release_id': 'fixture', 'status': 'accepted',
                'changes': [{'path': 'backend/example.py', 'candidate_sha256': candidate_hash}]}),
                encoding='utf-8')
            with patch('spark_insight_tools._known_release_store', return_value=store):
                report = json.loads(self._run(call))
        self.assertEqual(report['status'], 'ok')
        top = report['recent_releases'][-1]
        self.assertEqual(top['release_status'], 'accepted')
        self.assertEqual(top['candidate_sha256'][0], candidate_hash)

    def test_optional_and_argumentless_calls_accept_missing_args(self):
        async def call(loop):
            return (await loop.answer_mcp_tool("list_project_files", {}),
                    await loop.answer_mcp_tool("inspect_self", {}))

        results = self._run(call)
        for result in results:
            self.assertNotIn("Invalid", result)
        self.assertIn("version", results[1].lower())

    def test_missing_source_reports_not_found(self):
        async def call(loop):
            return await loop.answer_mcp_tool(
                "read_source_file", {"file_path": "no_such_module_xyz.py"})

        result = self._run(call)
        self.assertIn("not_found", result)
        self.assertIn("file not found: no_such_module_xyz.py", result)


class HonestyTests(_AudioLoopCase):
    """Results must distinguish unavailable access from missing source."""

    def test_backend_down_is_unavailable_not_ok(self):
        with patch("spark_insight_tools._fetch_loopback",
                   side_effect=OSError("connection refused")):
            report = backend_health()
        self.assertEqual(report["status"], "unavailable")
        self.assertIn("endpoint failed", report["message"])

    def test_backend_health_skips_dead_channels_but_keeps_live_state(self):
        def fake(endpoint):
            if endpoint == "/status":
                return {"ai_provider": "gemini", "live_state": "connected",
                        "live_profile": "cinematic", "audio_transport": "browser_aec",
                        "hands_free_ready": True, "live_error_code": None,
                        "live_message": ""}
            raise OSError("channel down")

        with patch("spark_insight_tools._fetch_loopback", side_effect=fake):
            report = backend_health()
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["backend"]["live_state"], "connected")
        self.assertEqual(report["channels"]["telegram"], "unavailable")
        self.assertEqual(report["channels"]["whatsapp"], "unavailable")

    def test_bad_regex_is_unavailable_not_notfound(self):
        self.assertEqual(search_spark_source("[def")["status"], "unavailable")
        self.assertEqual(search_spark_source(r"absolutely-nothing-xyz-$^")["status"],
                         "not_found")

    def test_git_failure_is_unavailable(self):
        with patch("spark_insight_tools.subprocess.run",
                   side_effect=OSError("git not installed")):
            report = git_state()
        self.assertEqual(report["status"], "unavailable")

    def test_missing_release_store_is_explicit(self):
        with patch("spark_insight_tools._known_release_store", return_value=None):
            report = release_summary()
        self.assertEqual(report["status"], "unavailable")
        self.assertIn("release store", report["message"])

    def test_secrets_never_routed_to_the_model(self):
        async def call(loop):
            out = []
            for name, args in (("read_source_file", {"file_path": ".env"}),
                               ("read_source_file", {"file_path": "spark_credential_store.py"}),
                               ("search_source_code", {"pattern": r"api_key\s*="})):
                out.append(await loop.answer_mcp_tool(name, args))
            return out

        results = self._run(call)
        # .env must be refused outright (not readable source).
        self.assertIn("refused", results[0])
        for result in results:
            for secret in ("AIzaSy", "gsk_", "sk-", "BEGIN PRIVATE KEY"):
                self.assertNotIn(secret, result)


class BudgetTests(unittest.TestCase):
    def test_rate_budget_still_enforced(self):
        import spark

        async def call():
            loop = spark.AudioLoop()
            for index in range(6):
                answer = await loop.answer_mcp_tool(
                    "read_source_file", {"file_path": f"f_missing_{index}.py"})
            return answer

        self.assertIn("rate limit", asyncio.run(call()))


if __name__ == "__main__":
    unittest.main()
