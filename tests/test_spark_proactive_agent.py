"""Capability 03 — Proactive agent offline acceptance.

Proposals, approvals, execution, undo and remembered choices all run against
a real sqlite store with injectable executors; restart-resume is covered by
reconstructing the agent over the same root.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_proactive_agent import (DEDUPE_WINDOW, ProactiveAgent, ProactiveError,
                                   Proposal)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.clock = 1_700_000_000.0
        self.agent = ProactiveAgent(self.root, clock=lambda: self.clock)
        self.results = []

    def propose(self, source="gmail", kind="read.unread_summary", tier="read_only",
                detail="Summarize unread mail"):
        proposal = Proposal(source, kind, tier, detail)
        return proposal, self.agent.propose(proposal)


class ProposalTests(Base):
    def test_proposal_validation(self):
        with self.assertRaises(ProactiveError):
            Proposal("carrier", "read.unread_summary", "read_only", "Text")
        with self.assertRaises(ProactiveError):
            Proposal("gmail", "read unread!", "read_only", "Text")
        with self.assertRaises(ProactiveError):
            Proposal("gmail", "read.unread", "admin", "Text")
        with self.assertRaises(ProactiveError):
            Proposal("gmail", "read.unread", "read_only", "")

    def test_read_only_proposal_queues_without_approval(self):
        proposal, queued = self.propose()
        self.assertTrue(queued["queued"])
        inbox = self.agent.inbox(state="proposed")
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["proposals"][0]["tier"], "read_only")

    def test_duplicates_within_window_are_not_reproposed(self):
        _proposal, first = self.propose()
        _proposal2, second = self.propose()
        self.assertTrue(first["queued"])
        self.assertFalse(second["queued"])
        self.assertEqual(second["reason"], "already proposed recently")
        self.clock += DEDUPE_WINDOW + 1
        _proposal3, third = self.propose()
        self.assertTrue(third["queued"])

    def test_restricted_tier_queues_but_never_executes(self):
        proposal, queued = self.propose(kind="device.lights_set", tier="restricted",
                                        detail="Living room lamp 100%")
        self.assertTrue(queued["queued"])
        with self.assertRaises(ProactiveError) as caught:
            self.agent.execute(queued["dedupe_key"])
        self.assertIn("never self-executed", str(caught.exception))

    def test_suggest_without_reversible_handler_is_refused(self):
        with self.assertRaises(ProactiveError):
            self.propose(kind="mail.purge", tier="suggest", detail="Purge unread mail")


class ApprovalAndExecutionTests(Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.undone = []
        self.agent.register_executor(
            "mail.snooze", "gmail",
            run=lambda detail: self.calls.append(detail) or {"snoozed": True},
            undo=lambda payload: self.undone.append(payload))

    def approve(self, kind="mail.snooze", remember=False, tier="suggest"):
        proposal = Proposal("gmail", kind, tier, "Snooze until tomorrow")
        queued = self.agent.propose(proposal)
        decision = self.agent.decide(queued["dedupe_key"], approved=True,
                                     remember=remember)
        return queued["dedupe_key"], decision

    def test_approval_flows_end_to_end_and_records_executor_result(self):
        key, decision = self.approve()
        self.assertTrue(decision["remembered"] is False)
        result = self.agent.execute(key)
        self.assertTrue(result["executed"])
        self.assertEqual(result["result"], {"snoozed": True})
        self.assertEqual(self.calls, ["Snooze until tomorrow"])
        self.assertEqual(self.agent.inbox(state="executed")["count"], 1)

    def test_execution_without_approval_is_refused(self):
        proposal = Proposal("gmail", "mail.snooze", "suggest", "Snooze until tomorrow")
        queued = self.agent.propose(proposal)
        with self.assertRaises(ProactiveError):
            self.agent.execute(queued["dedupe_key"])

    def test_executed_action_can_be_undone(self):
        key, _decision = self.approve()
        self.agent.execute(key)
        undone = self.agent.undo(key)
        self.assertTrue(undone["undone"])
        self.assertEqual(self.undone, [{"snoozed": True}])
        self.assertEqual(self.agent.inbox(state="undone")["count"], 1)

    def test_irreversible_actions_cannot_be_undone(self):
        # read-only tier has no undo requirement; execution is permitted only
        # with an executor registered, so register one WITHOUT undo.
        self.agent.register_executor("read.unread_summary", "gmail",
                                     run=lambda detail: {"count": 3}, undo=None)
        proposal = Proposal("gmail", "read.unread_summary", "read_only", "Summarize")
        queued = self.agent.propose(proposal)
        result = self.agent.execute(queued["dedupe_key"])
        self.assertTrue(result["executed"])
        with self.assertRaises(ProactiveError) as caught:
            self.agent.undo(queued["dedupe_key"])
        self.assertIn("not reversible", str(caught.exception))

    def test_executor_failure_becomes_recorded_failed_state(self):
        def broken(detail):
            raise OSError("provider offline")

        self.agent.register_executor("mail.snooze", "gmail", run=broken,
                                     undo=lambda payload: None)
        proposal = Proposal("gmail", "mail.snooze", "suggest", "Snooze until tomorrow")
        queued = self.agent.propose(proposal)
        self.agent.decide(queued["dedupe_key"], approved=True)
        result = self.agent.execute(queued["dedupe_key"])
        self.assertFalse(result["executed"])
        self.assertIn("provider offline", result["error"])
        self.assertEqual(self.agent.inbox(state="failed")["count"], 1)


class RememberedChoiceTests(Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.agent.register_executor("mail.snooze", "gmail",
                                     run=lambda detail: self.calls.append(detail),
                                     undo=lambda payload: None)

    def approve(self, remember=True):
        proposal = Proposal("gmail", "mail.snooze", "suggest", "Snooze until tomorrow")
        queued = self.agent.propose(proposal)
        self.agent.decide(queued["dedupe_key"], approved=True, remember=remember)
        return queued["dedupe_key"]

    def test_remembered_yes_auto_executes_future_same_pattern(self):
        first_key = self.approve(remember=True)
        self.agent.execute(first_key)
        proposal = Proposal("gmail", "mail.snooze", "suggest", "Snooze until tomorrow")
        second = self.agent.propose(proposal)
        result = self.agent.execute(second["dedupe_key"])
        self.assertTrue(result["executed"])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.agent.daily_summary()["executed"], 2)

    def test_remembered_choice_is_scoped_to_source(self):
        self.approve(remember=True)
        # Same action kind for a different source is refused at registration,
        # so a remembered Gmail yes can never authorize Slack actions.
        with self.assertRaises(ProactiveError) as caught:
            self.agent.register_executor("mail.snooze", "slack",
                                         run=lambda detail: None, undo=lambda p: None)
        self.assertIn("another source", str(caught.exception))
        self.assertFalse(self.agent.remembered("slack", "mail.snooze"))

    def test_denial_is_not_remembered_as_yes(self):
        proposal = Proposal("gmail", "mail.snooze", "suggest", "Snooze until tomorrow")
        queued = self.agent.propose(proposal)
        self.agent.decide(queued["dedupe_key"], approved=False)
        self.assertFalse(self.agent.remembered("gmail", "mail.snooze"))


class PersistenceTests(Base):
    def test_state_survives_restart_on_same_root(self):
        self.agent.register_executor("mail.snooze", "gmail",
                                     run=lambda d: {"ok": d}, undo=lambda p: None)
        proposal = Proposal("gmail", "mail.snooze", "suggest", "Snooze until tomorrow")
        queued = self.agent.propose(proposal)
        self.agent.decide(queued["dedupe_key"], approved=True)

        reborn = ProactiveAgent(self.root, clock=lambda: self.clock)
        reborn.register_executor("mail.snooze", "gmail",
                                 run=lambda d: {"ok": d}, undo=lambda p: None)
        key = queued["dedupe_key"]
        result = reborn.execute(key)
        self.assertTrue(result["executed"])
        self.assertEqual(reborn.inbox(state="executed")["count"], 1)
        summary = reborn.daily_summary()
        self.assertEqual(summary["proposed"], 1)
        self.assertEqual(summary["executed"], 1)


if __name__ == "__main__":
    unittest.main()
