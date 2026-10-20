"""Specialist agent workforce: a shared, role-scoped task interface (§6).

The master prompt asks for specialist agents executed by a shared model, with a
common task interface. This module supplies the *governance* half of that: a
registry of logical roles, each allowed to invoke only a scoped set of existing
engine actions, plus bounds and safety rules. It executes nothing itself — the
evolution dispatcher routes the inner action after the role check, so approval
gates, payload validation and journalled behaviour are inherited unchanged.

Rules:

* A role may only invoke actions in its allowlist. An unknown role or an
  out-of-scope action is refused.
* A role can never self-approve: inner actions carrying an `approved` field must
  pass `False`. Real approvals flow through the normal trusted route.
* Roles may not nest assignments (`workforce_assign` inside a role payload is
  forbidden), so authority cannot be laundered through a second role.
* Task text and remote content are data, never instructions; execution stays
  bounded by the inner engine's own limits (this module adds role *scoping*,
  not a new trust width).

Roles map to the master prompt's table. Titles whose backing actions route
through other session-gated boundaries (memory manager over the intelligence
service, integrator over MCP voice tools, file manager over the organizer) are
deliberately absent here — those agents keep their own existing gates rather
than gaining a second routing path. The registry lists only what actually
routes through the evolution dispatcher today.
"""


class WorkforceError(ValueError):
    pass


ROLES = {
    "planner": {
        "name": "Planner",
        "responsibility": "Goal decomposition and execution planning",
        "actions": frozenset(("saee_discover", "saee_registry", "saee_inventory", "saee_ledger")),
    },
    "researcher": {
        "name": "Researcher",
        "responsibility": "Repository and documentation research (read-only)",
        "actions": frozenset((
            "analyze_repository", "import_repository", "list_repository_analyses",
            "read_repository_analysis", "mcp_discover", "rea_discover",
        )),
    },
    "architect": {
        "name": "Architect",
        "responsibility": "Design and dependency decisions (advisory)",
        "actions": frozenset(("analyze_repository", "saee_discover")),
    },
    "developer": {
        "name": "Developer",
        "responsibility": "Code generation and refactoring via staged candidates",
        "actions": frozenset(("stage_repository_upgrade", "heal_sources")),
    },
    "tester": {
        "name": "Tester",
        "responsibility": "Run approved regression tests on staged candidates",
        "actions": frozenset(("list_repair_candidates", "test_repair_candidate",
                              "diagnose_sources")),
    },
    "security_auditor": {
        "name": "Security Auditor",
        "responsibility": "Secret scanning, static checks and source diagnosis",
        "actions": frozenset(("security_scan", "diagnose_sources")),
    },
    "repair_agent": {
        "name": "Repair Agent",
        "responsibility": "Fault diagnosis, bounded repair and rollback",
        "actions": frozenset((
            "diagnose_sources", "list_repairs", "list_repair_candidates",
            "test_repair_candidate", "rollback_repair", "self_heal_diagnose",
            "self_heal_recover", "heal_sources",
        )),
    },
    "performance_engineer": {
        "name": "Performance Engineer",
        "responsibility": "Profiling and before/after benchmark comparison",
        "actions": frozenset(("profile_import_cost", "profile_compare", "disk_forecast")),
    },
    "system_monitor": {
        "name": "System Monitor",
        "responsibility": "Environmental diagnosis and disk forecasting",
        "actions": frozenset(("self_heal_diagnose", "disk_forecast")),
    },
    "release_manager": {
        "name": "Release Manager",
        "responsibility": "Candidate activation review and rollback",
        "actions": frozenset(("list_repairs", "list_repair_candidates",
                              "activate_repair_candidate", "rollback_repair")),
    },
}

# Actions no role may ever route: workforce meta and anything with authority
# beyond a single already-scoped engine action.
FORBIDDEN_INNER = frozenset(("workforce_assign", "workforce_roles"))

# Safety-critical fields a role is not allowed to set truthfully.
NO_SELF_APPROVAL_FIELDS = ("approved",)


def roles_summary():
    """Describe the workforce registry. Verified flags are honest: actions are
    checked against the caller's dispatcher, not executed here."""
    return [
        {"id": role_id, "name": spec["name"],
         "responsibility": spec["responsibility"],
         "actions": sorted(spec["actions"])}
        for role_id, spec in sorted(ROLES.items())
    ]


def check_assignment(role, action, payload):
    """Validate a workforce assignment before the dispatcher sees it.

    Raises WorkforceError for unknown roles, out-of-scope actions, nested
    assignments, or self-approval attempts. Returns the (unchanged) action and
    payload so the caller can dispatch.
    """
    spec = ROLES.get(role)
    if spec is None:
        raise WorkforceError("Unknown workforce role.")
    if not isinstance(action, str) or action not in spec["actions"]:
        raise WorkforceError("Role %s may not invoke that action." % spec["name"])
    if action in FORBIDDEN_INNER:
        raise WorkforceError("Workforce meta actions cannot be routed by a role.")
    if not isinstance(payload, dict):
        raise WorkforceError("Role assignment payload must be an object.")
    for field in NO_SELF_APPROVAL_FIELDS:
        if field in payload and payload[field] is True:
            raise WorkforceError(
                "A specialist role cannot approve %s; approvals use the trusted route." % action)
    return action, payload
