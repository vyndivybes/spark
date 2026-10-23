"""Capabilities 08, 09 & 10 — Workbench wiring acceptance.

Specification search (honest planner gate), skill ecosystem (import review,
grant-gated pipelines, revoke) and agent runtimes (refuse-before-execute,
bounded steps, restricted CodeAct) all flow through real Workbench dispatch
with real spark workspace storage. No network and no live model calls.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError


class CapabilityWorkB2Tests(unittest.IsolatedAsyncioTestCase):
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

    async def test_actions_are_registered(self):
        for action in ("spec_search_status", "spec_search_run", "spec_candidates",
                       "spec_activate", "spec_rollback", "skill_import",
                       "skill_review", "skill_list", "skill_run", "skill_runs",
                       "skill_revoke", "skill_status", "agents_status",
                       "agents_react", "agents_codeact", "agents_recursive",
                       "agents_runs"):
            self.assertIn(action, ACTION_KEYS)

    async def test_spec_run_is_honest_without_a_granted_planner(self):
        result = await self.action("spec_search_run",
                                   goal="Improve the triage routing spec inline")
        self.assertEqual(result["status"], "planner_not_configured")
        status = await self.action("spec_search_status")
        self.assertEqual(status["runs_recorded"], 1)
        with self.assertRaises(WorkbenchError):
            await self.action("spec_search_run", goal="short")

    async def test_skill_import_requires_digest_and_owner_review_binds_grants(self):
        instructions = "Local reading of vault notes only."
        digest = __import__("hashlib").sha256(
            instructions.encode("utf-8")).hexdigest()
        with self.assertRaises(WorkbenchError):
            await self.action("skill_import", manifest={
                "name": "vault-reader", "description": "summarize vault note",
                "license": "Unknown", "provenance": "https://example.org/s",
                "sha256": digest, "instructions": instructions}, provided_by="f")
        imported = await self.action("skill_import", manifest={
            "name": "vault-reader", "description": "summarize vault note",
            "license": "MIT", "provenance": "https://example.org/s",
            "sha256": digest, "instructions": instructions,
            "requested_tools": ["search.obsidian"]}, provided_by="founder")
        self.assertEqual(imported["status"], "imported.unreviewed")
        with self.assertRaises(WorkbenchError):
            await self.action("skill_run", key=imported["key"], name="flow",
                              pipeline=[{"op": "search.obsidian"}], inputs={})
        with self.assertRaises(WorkbenchError):
            await self.action("skill_review", key=imported["key"],
                              approved_by="founder", granted_tools=["shell.exec"])
        reviewed = await self.action("skill_review", key=imported["key"],
                                     approved_by="founder",
                                     granted_tools=["search.obsidian"])
        self.assertEqual(reviewed["granted_tools"], ["search.obsidian"])

    async def test_granted_skill_pipeline_runs_and_revoke_rolls_back(self):
        instructions = "Read-only snapshot search."
        digest = __import__("hashlib").sha256(
            instructions.encode("utf-8")).hexdigest()
        imported = await self.action("skill_import", manifest={
            "name": "snapshot-reader", "description": "search snapshots",
            "license": "Apache-2.0", "provenance": "https://example.org/p",
            "sha256": digest, "instructions": instructions,
            "requested_tools": ["search.snapshots"]}, provided_by="founder")
        await self.action("skill_review", key=imported["key"],
                          approved_by="founder",
                          granted_tools=["search.snapshots"])
        ran = await self.action("skill_run", key=imported["key"],
                                name="lookup", pipeline=[
                                    {"op": "search.snapshots",
                                     "payload": {"q": "briefing"}}],
                                inputs={})
        self.assertEqual(ran["status"], "ran")
        revoked = await self.action("skill_revoke", key=imported["key"],
                                    approved_by="founder")
        self.assertTrue(revoked["rolled_back"])
        with self.assertRaises(WorkbenchError):
            await self.action("skill_run", key=imported["key"], name="again",
                              pipeline=[{"op": "search.snapshots"}], inputs={})

    async def test_react_refuses_unregistered_tools_without_executing(self):
        outcome = await self.action(
            "agents_react", goal="exfiltrate",
            steps=[{"action": {"tool": "shell.exec", "input": "dir"}}] * 12,
            grant_side_effects=False)
        self.assertEqual(outcome["status"], "step_budget_exhausted")
        self.assertTrue(all(step["kind"] == "refused" for step in outcome["steps"]))
        runs = await self.action("agents_runs", adapter="react", limit=5)
        self.assertEqual(len(runs), 1)

    async def test_react_granted_read_only_tool_answers_with_masking(self):
        outcome = await self.action(
            "agents_react", goal="find snapshots",
            steps=[{"action": {"tool": "search.snapshots", "input": "briefing"}},
                   {"final": "done GEMINI_API_KEY=abc123"}],
            grant_side_effects=False)
        self.assertEqual(outcome["status"], "answered")
        self.assertNotIn("abc123", outcome["answer"])

    async def test_codeact_refuses_io_and_evaluates_pure_math(self):
        with self.assertRaises(WorkbenchError):
            await self.action("agents_codeact", code="open('x')")
        with self.assertRaises(WorkbenchError):
            await self.action("agents_codeact", code="import os")
        result = await self.action("agents_codeact", code="20 + 22")
        self.assertEqual(result["result"], "42")

    async def test_recursive_decomposition_is_bounded_and_recorded(self):
        outcome = await self.action(
            "agents_recursive", goal="prepare digest",
            steps=[{"final": "one"}, {"final": "two"}],
            subgoals=["find items", "summarize"])
        self.assertEqual(outcome["status"], "decomposed")
        self.assertEqual(len(outcome["subgoals"]), 2)
        with self.assertRaises(WorkbenchError):
            await self.action("agents_recursive", goal="wide",
                              steps=[{"final": "f"}],
                              subgoals=["a", "b", "c", "d"])

    async def test_agents_status_documents_honest_sandbox_limits(self):
        status = await self.action("agents_status")
        self.assertIn("Not an OS-level sandbox", status["sandbox_note"])