"""Capability 10 — Bounded advanced agent runtimes (ReAct, CodeAct, recursive).

Three adapters share one hard contract:

* every tool must be pre-registered; side-effect tools additionally require
  an explicit per-run grant; unregistered or ungranted calls are refused
  *before* execution and recorded as observations;
* ReAct (think/act/observe) is bounded by steps and per-tool call counts;
* CodeAct runs through a strict AST-only expression interpreter: no imports,
  no attribute access, no function calls, no I/O of any kind. This is a
  restricted interpreter by construction — it is honestly NOT an OS-level
  sandbox, and the status report says so;
* the recursive adapter decomposes with a bounded depth (2) and width (3),
  each subtask re-entering the same guarded ReAct loop;
* everything a run emitted is masked with the shared redaction rules from
  spark_trace_learning before it is stored.
"""
from __future__ import annotations

import ast
import contextlib
import re
import sqlite3
import time
from pathlib import Path

from spark_trace_learning import mask_secrets

MAX_STEPS = 12
MAX_DEPTH = 2
MAX_WIDTH = 3
MAX_OUTPUT = 4000


class AgentRuntimeError(ValueError):
    """Unsafe or invalid agent runtime request."""


class Tool:
    def __init__(self, name, callback, *, side_effect=False, max_calls=2):
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,39}", name):
            raise AgentRuntimeError("Tool names are short lowercase tokens.")
        if not callable(callback):
            raise AgentRuntimeError("Tools are callables.")
        self.name = name
        self.callback = callback
        self.side_effect = bool(side_effect)
        self.max_calls = int(max_calls)


class RestrictedExpression:
    """AST-allowlisted pure expression evaluator for CodeAct."""

    ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
               ast.Load, ast.Tuple, ast.Compare, ast.BoolOp, ast.IfExp,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
               ast.USub, ast.UAdd, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
               ast.Gt, ast.GtE, ast.And, ast.Or, ast.Not, ast.Subscript,
               ast.Slice, ast.List, ast.Dict, ast.comprehension, ast.ListComp,
               ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.Expression)

    def evaluate(self, code, variables):
        if not isinstance(code, str) or len(code) > 2000 or "\n" in code:
            raise AgentRuntimeError("CodeAct input is one bounded expression.")
        try:
            tree = ast.parse(code.strip(), mode="eval")
        except SyntaxError as error:
            raise AgentRuntimeError("CodeAct expression is invalid: "
                                    + (str(error)[:100] or "parse error")) from None
        for node in ast.walk(tree):
            if not isinstance(node, self.ALLOWED):
                raise AgentRuntimeError("CodeAct refused node: "
                                        + type(node).__name__)
        if any(isinstance(node, ast.Pow) for node in ast.walk(tree)):
            raise AgentRuntimeError("CodeAct refuses exponentiation (unbounded "
                                    "magnitude).")
        variables = dict(variables or {})
        variables["__builtins__"] = {}
        try:
            globals_env = {"__builtins__": {}}  # no Python built-ins reachable
            result = eval(compile(tree, "<codeact>", "eval"),
                          globals_env, variables)
        except (ZeroDivisionError, NameError, TypeError, ValueError,
                RecursionError, MemoryError, IndexError, KeyError,
                AttributeError) as error:
            raise AgentRuntimeError("CodeAct evaluation failed safely: "
                                    + type(error).__name__) from None
        if isinstance(result, (int, float)) and abs(result) > 1e12:
            raise AgentRuntimeError("CodeAct result exceeds the magnitude bound.")
        text = result if isinstance(result, str) else repr(result)
        return text[:MAX_OUTPUT]


class ToolBox:
    def __init__(self):
        self._tools = {}
        self._used = {}

    def register(self, tool):
        if len(self._tools) >= 16:
            raise AgentRuntimeError("Bounded tool set is full.")
        if tool.name in self._tools:
            raise AgentRuntimeError("Tool already registered: " + tool.name)
        self._tools[tool.name] = tool
        self._used[tool.name] = 0
        return tool.name

    def call(self, name, payload, *, allow_side_effects):
        tool = self._tools.get(name)
        if tool is None:
            raise AgentRuntimeError("Unregistered tool refused: " + str(name))
        if tool.side_effect and not allow_side_effects:
            raise AgentRuntimeError("Side-effect tool is not granted for this run: "
                                    + tool.name)
        if self._used[name] >= tool.max_calls:
            raise AgentRuntimeError("Tool call budget exhausted: " + tool.name)
        self._used[name] += 1
        try:
            result = tool.callback(payload)
        except Exception as error:
            return {"tool": tool.name, "ok": False,
                    "error": type(error).__name__}
        text = result if isinstance(result, str) else repr(result)
        if len(text) > MAX_OUTPUT:
            raise AgentRuntimeError("Tool output exceeds the bound.")
        return {"tool": tool.name, "ok": True, "result": text[:400]}

    def tools(self, *, include_side_effects=False):
        return sorted(name for name, tool in self._tools.items()
                      if include_side_effects or not tool.side_effect)


class ReActRuntime:
    """Think→act→observe loop with hard refusal-before-execution semantics."""

    def __init__(self, toolbox, *, mask=mask_secrets, clock=time.time):
        self.box = toolbox
        self.mask = mask
        self.clock = clock

    def run(self, goal, model, *, side_effects_granted=False,
            initial_observations=None):
        if not callable(model):
            raise AgentRuntimeError("A scripted or live model callable is required.")
        observations = list(initial_observations or [])
        steps = []
        for index in range(MAX_STEPS):
            step = model({"goal": goal, "observations": observations,
                          "step": index, "tools": self.box.tools()})
            if not isinstance(step, dict) or not ({"think", "action", "final"}
                                                 >= set(step)):
                raise AgentRuntimeError("Model step must be think/action or final.")
            if "final" in step:
                steps.append({"step": index, "kind": "final",
                              "text": self.mask(str(step["final"]))[:400]})
                return {"status": "answered", "steps": steps,
                        "answer": self.mask(str(step["final"]))[:MAX_OUTPUT],
                        "steps_used": index + 1}
            act = step.get("action")
            if not isinstance(act, dict) or set(act) - {"tool", "input"}:
                raise AgentRuntimeError("Actions reference a tool and bounded input.")
            try:
                outcome = self.box.call(act["tool"], act.get("input"),
                                        allow_side_effects=side_effects_granted)
                observations.append(masked := self.mask(outcome.get(
                    "result") or outcome.get("error", ""))[:240])
                steps.append({"step": index, "kind": "tool", "tool": act["tool"],
                              "ok": outcome["ok"],
                              "text": self.mask(str(step.get("think", "")))[:200]})
            except AgentRuntimeError as error:
                observations.append(self.mask(str(error))[:240])
                steps.append({"step": index, "kind": "refused",
                              "tool": act.get("tool"),
                              "text": self.mask(str(step.get("think", "")))[:200]})
        return {"status": "step_budget_exhausted", "steps": steps,
                "answer": None, "steps_used": MAX_STEPS}


class RecursiveRuntime:
    """Bounded decomposition; subgoals re-enter the guarded ReAct loop."""

    def __init__(self, react, *, mask=mask_secrets):
        self.react = react
        self.mask = mask

    def run(self, goal, model, planner, *, depth=MAX_DEPTH):
        if not callable(planner):
            raise AgentRuntimeError("A planner callable is required.")
        subgoals = planner(goal)
        if not isinstance(subgoals, list) or len(subgoals) > MAX_WIDTH:
            raise AgentRuntimeError("Decomposition is bounded at 3 subgoals.")
        if depth <= 0:
            raise AgentRuntimeError("Recursion depth budget exhausted; refuse to "
                                    "decompose further.")
        results = []
        for subgoal in subgoals:
            if not isinstance(subgoal, str) or not 1 <= len(subgoal) <= 300:
                raise AgentRuntimeError("Subgoals are bounded strings.")
        for subgoal in subgoals:
            outcome = self.react.run(subgoal, model)
            results.append({"subgoal": self.mask(subgoal)[:200],
                            **{key: outcome[key] for key in
                               ("status", "steps_used")}})
        return {"status": "decomposed", "depth": depth,
                "subgoals": results}


class AgentRuntimes:
    """Facade + SQLite run ledger used by the workbench."""

    KEEP_RUNS = 100

    def __init__(self, root, *, clock=time.time, mask=mask_secrets):
        self.root = Path(root) / "agent-runtimes"
        self.clock = clock
        self.mask = mask
        if self.root.is_symlink():
            raise AgentRuntimeError("Linked runtime storage is prohibited.")
        self.box = ToolBox()
        self.react = ReActRuntime(self.box, mask=mask, clock=clock)
        self.recursive = RecursiveRuntime(self.react, mask=mask)
        self.codeact = RestrictedExpression()

    def register(self, tool, *, adapter="react"):
        """Attach a tool to the guarded ReAct toolbox of a specific adapter."""
        if adapter != "react":
            raise AgentRuntimeError("Tools attach to the react toolbox only.")
        return self.box.register(tool)

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "runs.sqlite3"
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS runs("
                           "key TEXT PRIMARY KEY,adapter TEXT,goal TEXT,"
                           "status TEXT,steps TEXT,answer TEXT,created REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    def record_run(self, adapter, goal, status, steps, answer):
        key = "ar-" + str(int(self.clock() * 1_000_000))
        with self._db() as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                       (key, adapter, self.mask(str(goal))[:200], status,
                        self.mask(str(steps))[:8000],
                        self.mask(str(answer))[:MAX_OUTPUT] if answer else None,
                        self.clock()))
            db.execute("DELETE FROM runs WHERE key NOT IN (SELECT key FROM runs "
                       "ORDER BY created DESC LIMIT ?)", (self.KEEP_RUNS,))
        return key

    def runs(self, adapter=None, *, limit=50):
        with self._db() as db:
            if adapter:
                rows = db.execute("SELECT * FROM runs WHERE adapter=? ORDER BY "
                                  "created DESC LIMIT ?",
                                  (adapter, int(limit))).fetchall()
            else:
                rows = db.execute("SELECT * FROM runs ORDER BY created DESC "
                                  "LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    def status(self):
        return {"adapters": ["react", "codeact", "recursive"],
                "tools_registered": self.box.tools(include_side_effects=True),
                "side_effect_tools": [name for name in
                                      self.box.tools(include_side_effects=True)],
                "max_steps": MAX_STEPS, "max_depth": MAX_DEPTH,
                "codeact_scope": "AST allowlisted pure expressions; no "
                                 "imports, calls, attributes or I/O",
                "sandbox_note": "Not an OS-level sandbox; bounded interpreter "
                                "and tool grants by construction only"}
