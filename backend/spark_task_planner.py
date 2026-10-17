"""Stage 8 planning adapter for SPARK.

Converts a constrained, structured plan into a pending Task for review.
No execution or permissions are granted by creating a plan. Remote model
text is not parsed as a shell command or used as an executable.
"""
from spark_task_engine import MAX_STEPS, Step, Task

ALLOWED_ACTIONS = frozenset(("launch_desktop_app", "read_file", "read_directory"))
ALLOWED_APPS = frozenset(("notepad", "calculator", "paint"))


def prepare_task(description, proposed_steps):
    if not isinstance(proposed_steps, list) or not 1 <= len(proposed_steps) <= MAX_STEPS:
        raise ValueError("Invalid proposed step count")
    steps = []
    for candidate in proposed_steps:
        if not isinstance(candidate, dict) or set(candidate) != {"action", "args"}:
            raise ValueError("Invalid proposed step")
        action, args = candidate["action"], candidate["args"]
        if action not in ALLOWED_ACTIONS or not isinstance(args, dict):
            raise ValueError("Unsupported task action")
        if action == "launch_desktop_app":
            if set(args) != {"app"} or args["app"] not in ALLOWED_APPS:
                raise ValueError("Desktop application not allowed")
        else:
            # File reads are intentionally withheld from autonomous execution
            # until path-scoping and Windows authorization have been qualified.
            raise ValueError("File operations not enabled in task execution")
        steps.append(Step(action=action, args=dict(args)))
    return Task(description=description, steps=steps)


def task_preview(task):
    """Only metadata needed by a future approval UI; no action execution."""
    return {
        "task_id": task.id,
        "description": task.description,
        "status": task.status.value,
        "steps": [{"action": s.action, "args": dict(s.args), "status": s.status.value}
                  for s in task.steps],
        "requires_explicit_approval": True,
    }
