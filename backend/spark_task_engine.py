"""Bounded, approval-gated orchestration for SPARK agent tasks.

This module is offline, dependency-free and has no shell/browser privileges.
Executors are injected by the host only after the user approves each action.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
import uuid

MAX_STEPS = 12
MAX_RETRIES = 2
MAX_TEXT = 1000


class State(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Step:
    action: str
    args: dict = field(default_factory=dict)
    status: State = State.PENDING
    attempts: int = 0
    result: str = ""


@dataclass
class Task:
    description: str
    steps: list
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: State = State.PENDING
    cursor: int = 0
    audit: list = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.description, str) or not self.description.strip() or len(self.description) > MAX_TEXT:
            raise ValueError("Invalid task description")
        if not self.steps or len(self.steps) > MAX_STEPS:
            raise ValueError("A task requires 1-12 steps")
        if any(not isinstance(s, Step) or not isinstance(s.action, str) or not s.action for s in self.steps):
            raise ValueError("Invalid task step")
        self.audit.append("Task created; actions require explicit approval.")

    def current(self):
        return self.steps[self.cursor] if self.cursor < len(self.steps) else None

    def request_approval(self):
        if self.status in (State.CANCELLED, State.COMPLETED, State.FAILED):
            raise ValueError("Task is terminal")
        step = self.current()
        if step is None:
            raise ValueError("No remaining steps")
        if step.status == State.AWAITING_APPROVAL:
            return step
        if step.status != State.PENDING:
            raise ValueError("Step not ready")
        step.status = State.AWAITING_APPROVAL
        self.status = State.AWAITING_APPROVAL
        self.audit.append("Approval requested for step " + str(self.cursor + 1))
        return step

    def execute_approved(self, approved: bool, executor: Callable, verifier: Callable):
        if self.status != State.AWAITING_APPROVAL:
            raise ValueError("Step has no outstanding approval")
        step = self.current()
        if not approved:
            step.status = State.CANCELLED
            self.status = State.CANCELLED
            self.audit.append("User denied action")
            return self.status
        if not callable(executor) or not callable(verifier):
            raise ValueError("Executor and verifier are required")
        self.status = step.status = State.RUNNING
        # Only retry on explicitly declared transient failures from execution.
        for attempt in range(MAX_RETRIES + 1):
            step.attempts += 1
            try:
                outcome = executor(step.action, dict(step.args))
            except TransientExecutionError:
                if attempt < MAX_RETRIES:
                    continue
                step.result = "Transient action failed after bounded retries"
                break
            except Exception:
                step.result = "Action or verification failed; no automatic retry"
                break
            try:
                # Verification is mandatory and fail-closed. Once execution
                # succeeded, verification or formatting must never repeat it.
                if not bool(verifier(step.action, dict(step.args), outcome)):
                    raise RuntimeError("Verification failed")
                step.result = str(outcome)[:MAX_TEXT]
                step.status = State.COMPLETED
                self.cursor += 1
                self.status = State.COMPLETED if self.cursor == len(self.steps) else State.PENDING
                self.audit.append("Verified step " + str(self.cursor))
                return self.status
            except Exception:
                step.result = "Action or verification failed; no automatic retry"
                break
        step.status = self.status = State.FAILED
        self.audit.append("Step failed; execution halted")
        return self.status

    def cancel(self):
        if self.status not in (State.COMPLETED, State.CANCELLED, State.FAILED):
            self.status = State.CANCELLED
            step = self.current()
            if step:
                step.status = State.CANCELLED
            self.audit.append("Task cancelled")


class TransientExecutionError(Exception):
    """Host-declared retryable failure; never use for uncertain side effects."""
