"""Capability 10 — Advanced agent runtimes self-tests.

Scripted models (no network), hard refusals before execution, bounded
budgets, restricted CodeAct expressions and recursive decomposition gates.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_agent_runtimes import (AgentRuntimes, AgentRuntimeError, MAX_STEPS,
                                  ReActRuntime, RecursiveRuntime,
                                  RestrictedExpression, Tool, ToolBox)


def script(steps):
    """Deterministic scripted model that yields prewritten steps."""
    queue = list(steps)

    def model(state):
        if not queue:
            return {"final": "done"}
        return queue.pop(0)
    return model


def repeat(action):
    """Scripted model that always returns the same step (never finalizes)."""
    return lambda state: dict(action)


class CodeActTests(unittest.TestCase):
    def setUp(self):
        self.codeact = RestrictedExpression()

    def test_pure_arithmetic_and_comparisons_are_allowed(self):
        self.assertEqual(self.codeact.evaluate("40 + 2", {}),
                         "42")
        self.assertEqual(self.codeact.evaluate("1 < 2", {}), "True")
        self.assertEqual(self.codeact.evaluate("'a' in [1,2] if False else 7", {}),
                         "7")

    def test_imports_calls_attributes_and_io_are_refused(self):
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("import os", {})
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("len(variables)", {})
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("getattr(x, 'secret')", {})
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("(lambda: 1)()", {})
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("open('x').read()", {})

    def test_exponentiation_and_huge_results_are_refused(self):
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("99 ** 99", {})
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("10 ** 2", {})

    def test_evaluation_failures_are_safe_and_named(self):
        with self.assertRaises(AgentRuntimeError) as caught:
            self.codeact.evaluate("missing + 1", {})
        self.assertIn("NameError", str(caught.exception))
        with self.assertRaises(AgentRuntimeError):
            self.codeact.evaluate("1 / 0", {})


class ToolBoxTests(unittest.TestCase):
    def test_unregistered_and_budget_exhausted_tools_are_refused(self):
        box = ToolBox()
        box.register(Tool("calc.double", lambda payload: payload * 2,
                          max_calls=1))
        with self.assertRaises(AgentRuntimeError):
            box.call("shell.exec", {}, allow_side_effects=True)
        self.assertEqual(box.call("calc.double", 21,
                                  allow_side_effects=True)["result"], "42")
        with self.assertRaises(AgentRuntimeError):
            box.call("calc.double", 21, allow_side_effects=True)

    def test_duplicate_registration_is_refused(self):
        box = ToolBox()
        box.register(Tool("calc.double", lambda payload: payload * 2))
        with self.assertRaises(AgentRuntimeError):
            box.register(Tool("calc.double", lambda payload: payload))


def read_tool(payload):
    return "read:" + str(payload)[:20]


def write_tool(payload):
    return "written"


class ReActTests(unittest.TestCase):
    def setUp(self):
        self.box = ToolBox()
        self.box.register(Tool("search.notes", read_tool))
        self.box.register(Tool("files.write", write_tool, side_effect=True,
                               max_calls=1))
        self.react = ReActRuntime(self.box)

    def test_react_happy_path_ends_in_final_answer(self):
        model = script([
            {"think": "look up the note", "action": {"tool": "search.notes",
                                                     "input": "invoice"}},
            {"final": "Invoice noted."},
        ])
        outcome = self.react.run("summarize invoices", model)
        self.assertEqual(outcome["status"], "answered")
        self.assertEqual(outcome["answer"], "Invoice noted.")

    def test_side_effect_tool_without_explicit_grant_is_refused_before_running(self):
        calls = []
        def guarded(payload):
            calls.append(payload)
            raise AssertionError("must never run")
        box = ToolBox()
        box.register(Tool("files.write", guarded, side_effect=True))
        react = ReActRuntime(box)
        model = repeat({"action": {"tool": "files.write", "input": "x"}})
        outcome = react.run("write file", model)
        self.assertEqual(outcome["status"], "step_budget_exhausted")
        self.assertEqual(outcome["steps_used"], MAX_STEPS)
        self.assertTrue(all(step["kind"] == "refused" for step in outcome["steps"]))
        self.assertEqual(calls, [])

    def test_side_effect_tool_with_explicit_grant_runs(self):
        model = script([{"action": {"tool": "files.write", "input": "x"}},
                        {"final": "done"}])
        outcome = self.react.run("write file", model, side_effects_granted=True)
        self.assertEqual(outcome["status"], "answered")

    def test_unregistered_tool_refused_then_budget_exhausted(self):
        model = repeat({"action": {"tool": "shell.exec", "input": "dir"}})
        outcome = self.react.run("run shell", model)
        self.assertEqual(outcome["status"], "step_budget_exhausted")
        self.assertTrue(all(s["kind"] == "refused" for s in outcome["steps"]))

    def test_secrets_are_masked_in_recorded_steps(self):
        model = script([
            {"action": {"tool": "search.notes",
                        "input": "GEMINI_API_KEY=abc123"}},
            {"final": "GEMINI_API_KEY=abc123 in note"},
        ])
        outcome = self.react.run("summarize", model)
        self.assertNotIn("abc123", outcome["answer"])
        self.assertIn("GEMINI_API_KEY=<redacted>", outcome["answer"])

    def test_invalid_step_shapes_are_refused(self):
        with self.assertRaises(AgentRuntimeError):
            self.react.run("x", lambda state: "not-a-step")
        with self.assertRaises(AgentRuntimeError):
            self.react.run("x", lambda state: {"action": {"tool": "search.notes",
                                                          "input": {}, "extra": 1}})


class RecursiveTests(unittest.TestCase):
    def setUp(self):
        box = ToolBox()
        box.register(Tool("search.notes", read_tool))
        self.recursive = RecursiveRuntime(ReActRuntime(box))

    def test_bounded_decomposition_with_scripted_model(self):
        model = script([{"final": "part one"}, {"final": "part two"}])
        planner = lambda goal: ["find invoices", "summarize totals"]
        outcome = self.recursive.run("prepare digest", model, planner)
        self.assertEqual(outcome["status"], "decomposed")
        self.assertEqual([r["status"] for r in outcome["subgoals"]],
                         ["answered", "answered"])

    def test_width_and_depth_bounds_are_enforced(self):
        with self.assertRaises(AgentRuntimeError):
            self.recursive.run("x", lambda s: {"final": "f"},
                               lambda goal: ["a", "b", "c", "d"])
        with self.assertRaises(AgentRuntimeError):
            self.recursive.run("x", lambda s: {"final": "f"},
                               lambda goal: ["a"], depth=0)


class LedgerTests(unittest.TestCase):
    def test_runs_are_recorded_masked_and_compacted(self):
        dir_temp = tempfile.TemporaryDirectory()
        self.addCleanup(dir_temp.cleanup)
        runtimes = AgentRuntimes(dir_temp.name)
        runtimes.register(Tool("search.notes", read_tool), adapter="react")
        self.assertIn("search.notes", runtimes.status()["tools_registered"])
        key = runtimes.record_run("react", "summarize GEMINI_API_KEY=abc123",
                                  "answered", [{"step": 0}], "answer")
        runs = runtimes.runs("react")
        self.assertEqual(runs[0]["key"], key)
        self.assertNotIn("abc123", runs[0]["goal"])
        status = runtimes.status()
        self.assertIn("Not an OS-level sandbox", status["sandbox_note"])

    def test_register_adapter_validation(self):
        dir_temp = tempfile.TemporaryDirectory()
        self.addCleanup(dir_temp.cleanup)
        runtimes = AgentRuntimes(dir_temp.name)
        runtimes.register(Tool("search.notes", read_tool), adapter="react")
        with self.assertRaises(AgentRuntimeError):
            runtimes.register(Tool("BadName", lambda p: p), adapter="react")
        with self.assertRaises(AgentRuntimeError):
            runtimes.register(Tool("search.notes", lambda p: p), adapter="react")
        with self.assertRaises(AgentRuntimeError):
            runtimes.register(Tool("search.notes.2", read_tool), adapter="nope")


if __name__ == "__main__":
    unittest.main()
