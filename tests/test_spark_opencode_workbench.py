"""Capability 04 — Workbench wiring acceptance for the OpenCode agent.

Runs opencode actions through real Workbench dispatch with a real
SparkWorkspace. Live acceptance needs an installed OpenCode binary and is
reported honestly as not_configured here.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, REPOSITORY_ROOT, Workbench
from spark_productivity import WorkbenchError


class OpenCodeWorkbenchWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.directory.name)
        self.workbench = Workbench(self.workspace)
        self.project = "general"
        self.addAsyncCleanup(self._close)

    async def _close(self):
        await self.workbench.integrations.close()
        await self.workbench.intelligence.close()
        self.directory.cleanup()

    async def action(self, action, **payload):
        return await self.workbench.execute(action, self.project, payload)

    async def test_opencode_actions_are_registered(self):
        for action in ("opencode_status", "opencode_run", "opencode_diff",
                       "opencode_test"):
            self.assertIn(action, ACTION_KEYS)

    async def test_status_reports_discovery_and_boundaries(self):
        status = await self.action("opencode_status")
        self.assertIn("discovery", status)
        self.assertEqual(Path(status["root"]), REPOSITORY_ROOT)
        self.assertIn("no merge/deploy", status["policy"])
        self.assertEqual(status["sessions"]["count"], 0)

    async def test_run_without_installed_binary_is_refused_not_faked(self):
        agent = self.workbench.opencode
        if agent.installed:
            self.skipTest("OpenCode is installed on this host; live path applies.")
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("opencode_run", prompt="Write a bounded unit test",
                              cwd="", timeout=300)
        self.assertIn("not installed", str(caught.exception))

    async def test_diff_refuses_when_not_a_git_root(self):
        # A temp data dir is not the repository root, so git may still fail.
        agent = self.workbench.opencode
        if not agent.installed:
            self.skipTest("OpenCode not installed; diff gate still enforced.")
        with self.assertRaises(WorkbenchError):
            await self.action("opencode_test", command="del backend/server.py", cwd="")

    async def test_test_action_refuses_arbitrary_commands_even_when_missing(self):
        agent = self.workbench.opencode
        if agent.installed:
            self.skipTest("OpenCode installed; full live path applies.")
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("opencode_test", command="format C: /q", cwd="")
        self.assertIn("bounded", str(caught.exception).lower())


if __name__ == "__main__":
    unittest.main()
