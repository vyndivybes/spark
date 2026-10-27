"""Stage 8: bounded task planning and fail-closed approvals."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "backend" / "spark_task_engine.py"
spec = importlib.util.spec_from_file_location("spark_task_engine", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TaskEngineTests(unittest.TestCase):
    def new_task(self):
        return m.Task("Open approved tool", [m.Step("notepad"), m.Step("verify_output")])

    def test_requires_approval_and_individual_step_gates(self):
        t = self.new_task()
        called = []
        with self.assertRaises(ValueError):
            t.execute_approved(True, lambda *_: called.append("bad"), lambda *_: True)
        t.request_approval()
        self.assertEqual(t.execute_approved(True, lambda action, args: called.append(action) or "OK", lambda *_: True), m.State.PENDING)
        self.assertEqual(called, ["notepad"])
        self.assertEqual(t.current().action, "verify_output")
        with self.assertRaises(ValueError):
            t.execute_approved(True, lambda *_: "bad", lambda *_: True)
        t.request_approval()
        self.assertEqual(t.execute_approved(True, lambda *_: "ok", lambda *_: True), m.State.COMPLETED)

    def test_denial_never_executes(self):
        t = self.new_task()
        t.request_approval()
        called = []
        self.assertEqual(t.execute_approved(False, lambda *_: called.append(True), lambda *_: True), m.State.CANCELLED)
        self.assertEqual(called, [])

    def test_verification_failure_does_not_repeat_side_effect(self):
        t = self.new_task()
        t.request_approval()
        actions = []
        self.assertEqual(t.execute_approved(True, lambda *_: actions.append(True), lambda *_: False), m.State.FAILED)
        self.assertEqual(len(actions), 1)

    def test_transient_verifier_failure_never_repeats_an_executed_action(self):
        task = self.new_task()
        task.request_approval()
        actions = []
        checks = []

        def verify(*_):
            checks.append(True)
            if len(checks) == 1:
                raise m.TransientExecutionError('Verification transport failed')
            return True

        self.assertEqual(task.execute_approved(True, lambda *_: actions.append(True) or 'done', verify), m.State.FAILED)
        self.assertEqual(len(actions), 1)
        self.assertEqual(len(checks), 1)
        self.assertEqual(task.steps[0].attempts, 1)
        self.assertEqual(task.cursor, 0)

    def test_transient_result_formatting_failure_never_repeats_an_executed_action(self):
        task = self.new_task()
        task.request_approval()
        actions = []

        class Outcome:
            def __str__(self):
                raise m.TransientExecutionError('Formatting failed after successful execution')

        self.assertEqual(task.execute_approved(True, lambda *_: actions.append(True) or Outcome(), lambda *_: True), m.State.FAILED)
        self.assertEqual(len(actions), 1)
        self.assertEqual(task.steps[0].attempts, 1)
        self.assertEqual(task.cursor, 0)

    def test_retry_is_bounded(self):
        t = self.new_task()
        t.request_approval()
        calls = []
        def fail(*_):
            calls.append(True)
            raise m.TransientExecutionError()
        self.assertEqual(t.execute_approved(True, fail, lambda *_: True), m.State.FAILED)
        self.assertEqual(len(calls), m.MAX_RETRIES + 1)

    def test_executor_transient_failure_recovers_then_verifies_once(self):
        task = self.new_task()
        task.request_approval()
        actions = []
        checks = []

        def execute(*_):
            actions.append(True)
            if len(actions) == 1:
                raise m.TransientExecutionError('Try the execution again')
            return 'OK'

        self.assertEqual(task.execute_approved(True, execute, lambda *_: checks.append(True) or True), m.State.PENDING)
        self.assertEqual(len(actions), 2)
        self.assertEqual(len(checks), 1)
        self.assertEqual(task.steps[0].attempts, 2)
        self.assertEqual(task.cursor, 1)

    def test_limits_and_cancel(self):
        with self.assertRaises(ValueError):
            m.Task("too many", [m.Step("go") for _ in range(13)])
        t = self.new_task()
        t.cancel()
        with self.assertRaises(ValueError):
            t.request_approval()


if __name__ == "__main__":
    unittest.main()
