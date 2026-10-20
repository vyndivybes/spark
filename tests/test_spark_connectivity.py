import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_connectivity import STATES, Connectivity, ConnectivityError
from spark_evolution import Evolution, ACTION_KEYS, MaintenanceError
from spark_workspace import SparkWorkspace


def fake_integrations(config=None, history=None, execute=None):
    class FakeIntegrations:
        def catalog(self):
            if config is None:
                raise ValueError("bad config")
            if isinstance(config, Exception):
                raise config
            return config

        def history(self):
            return list(history or [])

        async def execute(self, server, action, args):
            if execute is not None:
                return execute(server, action, args)
            return [{"name": "read_only_tool"}]

    return FakeIntegrations()


def connectivity(env=None, exists=False, which=None, audit=None, config=None, history=None, execute=None):
    return Connectivity(
        root=Path("/") / "spark",
        integrations=fake_integrations(config=config, history=history, execute=execute),
        env=env or {},
        exists=lambda target: exists,
        which=which or (lambda name: None),
        clock=lambda: 1_000_000.0,
        homedir="/home/tester",
    )


class StaticClassificationTests(unittest.TestCase):
    def report(self, **kwargs):
        self.result = asyncio.run(connectivity(**kwargs).report())
        return self.result

    def test_states_and_labels_are_honest(self):
        self.report()
        for entry in self.result["entries"]:
            self.assertIn(entry["state"], STATES, entry["name"])
            self.assertTrue(entry["evidence"], entry["name"])

    def test_tenth_section_names_all_classified(self):
        self.report()
        names = {entry["name"] for entry in self.result["entries"]}
        for required in ("Graphify", "Graphiti", "Hermes", "REA", "Obsidian", "VAOS",
                         "VYNDI OS", "VEDM", "GitHub", "Google Drive", "Gmail",
                         "LLM providers", "Voice and multimodal services"):
            self.assertIn(required, names)

    def test_nothing_configured_reports_not_installed(self):
        self.report(config={})
        states = {entry["name"]: entry["state"] for entry in self.result["entries"]}
        for name in ("GitHub", "Gmail", "Graphify", "Graphiti", "Hermes", "REA"):
            self.assertEqual(states[name], "not installed", name)
        self.assertEqual(states["LLM providers"], "not installed")
        self.assertEqual(states["Voice and multimodal services"], "installed but disconnected")

    def test_configured_with_recent_audit_is_partially_operational(self):
        config = {"github": {"command": "npx", "args": [], "read_tools": ["list_repos"]}}
        history = [{"server": "github", "ok": True, "at": 999_000.0}]
        self.report(config=config, history=history)
        github = next(entry for entry in self.result["entries"] if entry["name"] == "GitHub")
        self.assertEqual(github["state"], "partially operational")
        self.assertEqual(github["server"], "github")

    def test_configured_without_audit_is_installed_but_disconnected(self):
        config = {"gmail": {"command": "npx", "args": [], "read_tools": ["read"]}}
        self.report(config=config)
        gmail = next(entry for entry in self.result["entries"] if entry["name"] == "Gmail")
        self.assertEqual(github_state(gmail), "installed but disconnected")

    def test_stale_audit_does_not_count(self):
        config = {"github": {"command": "npx", "args": [], "read_tools": []}}
        history = [{"server": "github", "ok": True, "at": 100_000.0}]
        self.report(config=config, history=history)
        github = next(entry for entry in self.result["entries"] if entry["name"] == "GitHub")
        self.assertEqual(github["state"], "installed but disconnected")

    def test_invalid_registration_reports_unknown(self):
        self.report(config=ValueError("nope"))
        states = {entry["name"]: entry["state"] for entry in self.result["entries"]}
        self.assertEqual(states["MCP registration"], "unknown")
        self.assertEqual(states["GitHub"], "unknown")
        self.assertEqual(states["Graphify"], "unknown")

    def test_rea_command_is_installed_but_disconnected(self):
        self.report(env={"SPARK_REA_COMMAND": "C:/tools/rea.exe"})
        rea = next(entry for entry in self.result["entries"] if entry["name"] == "REA")
        self.assertEqual(rea["state"], "installed but disconnected")
        self.assertNotIn("server", rea)

    def test_rea_falls_back_to_npx_route(self):
        self.report(which=lambda name: name == "npx" and "C:/npx")
        rea = next(entry for entry in self.result["entries"] if entry["name"] == "REA")
        self.assertEqual(rea["state"], "installed but disconnected")

    def test_keys_never_echoed(self):
        report = self.report(env={"GROQ_API_KEY": "gsk_super_secret_value",
                                  "GEMINI_API_KEY": "gemini_super_secret"})
        self.assertEqual(next(e for e in report["entries"] if e["name"] == "LLM providers")["state"],
                         "partially operational")
        self.assertNotIn("gsk_super_secret_value", json.dumps(report))
        self.assertNotIn("gemini_super_secret", json.dumps(report))


def github_state(entry):
    return entry["state"]


class ProbeTests(unittest.TestCase):
    def test_deep_probe_verifies_configured_services(self):
        config = {"graphify": {"command": "x", "args": [], "read_tools": ["query_spark_graph"]},
                  "github": {"command": "npx", "args": [], "read_tools": ["list_repos"]}}
        result = asyncio.run(connectivity(config=config).report(deep=True))
        self.assertEqual(result["probed"], 2)
        for entry in result["entries"]:
            if entry["name"] in ("Graphify", "GitHub"):
                self.assertEqual(entry["state"], "verified operational", entry)
                self.assertTrue(entry["probe"]["ok"], entry)
                self.assertEqual(entry["probe"]["tools"], 1)
                self.assertTrue(result["note"].startswith("Round-trip probe"))

    def test_probe_failure_reports_failed_verification(self):
        def execute(server, action, args):
            raise RuntimeError("tool schema invalid")
        config = {"github": {"command": "npx", "args": [], "read_tools": []}}
        result = asyncio.run(connectivity(config=config, execute=execute).report(deep=True))
        github = next(e for e in result["entries"] if e["name"] == "GitHub")
        self.assertEqual(github["state"], "failed verification")

    def test_probe_failure_message_is_truncated(self):
        def execute(server, action, args):
            raise RuntimeError("E" * 500)
        config = {"github": {"command": "npx", "args": [], "read_tools": []}}
        result = asyncio.run(connectivity(config=config, execute=execute).report(deep=True))
        github = next(e for e in result["entries"] if e["name"] == "GitHub")
        self.assertLessEqual(len(github["probe"]["error"]), 200)

    def test_vaos_jarvis_session_probe_is_skipped(self):
        config = {"vaos-jarvis": {"read_tools": ["ask_vaos_jarvis"]}}
        probes = []
        def execute(server, action, args):
            probes.append(server)
            return []
        result = asyncio.run(connectivity(config=config, execute=execute).report(deep=True))
        self.assertEqual(result["probed"], 0)
        self.assertEqual(probes, [])
        jarvis = next(e for e in result["entries"] if e["name"] == "VAOS Jarvis")
        self.assertEqual(jarvis["state"], "installed but disconnected")

    def test_static_report_never_probes(self):
        probes = []
        def execute(server, action, args):
            probes.append(server)
            return []
        config = {"github": {"command": "npx", "args": [], "read_tools": []}}
        result = asyncio.run(connectivity(config=config, execute=execute).report())
        self.assertEqual(result["deep"], False)
        self.assertEqual(result["probed"], 0)
        self.assertEqual(probes, [])
        self.assertTrue(result["note"].startswith("Static classification"))


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.temp.name)
        self.engine = Evolution(self.workspace, generator=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model call")))

    def tearDown(self):
        self.temp.cleanup()

    def test_action_key_requires_deep_flag(self):
        self.assertEqual(ACTION_KEYS["connectivity_report"], {"deep"})

    def test_dispatch_returns_entries(self):
        report = asyncio.run(self.engine.execute("connectivity_report", "general", {"deep": False}))
        self.assertIn("entries", report)
        self.assertEqual(report["deep"], False)
        self.assertTrue(all(entry["state"] in STATES for entry in report["entries"]))

    def test_dispatch_rejects_non_bool_deep(self):
        with self.assertRaises(MaintenanceError):
            asyncio.run(self.engine.execute("connectivity_report", "general", {"deep": "yes"}))

    def test_invalid_label_refused(self):
        with self.assertRaises(ConnectivityError):
            connectivity()._entry("Anything", "magic state", "evidence")


if __name__ == "__main__":
    unittest.main()
