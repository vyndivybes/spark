"""Offline cockpit gate for the OpenJarvis capability surface.

The real `workspace_action` handler is executed from the server source
(established fixture pattern): read-only capability actions must stay
available to the token-authorized cockpit even when no voice session is
running, while every mutating capability action keeps the live owner gate.
"""
import asyncio
import ast
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from spark_workbench import ACTION_KEYS as WORKBENCH_ACTIONS, WorkbenchError
from spark_workbench_voice import CAPABILITY_READ_ONLY_ACTIONS
from spark_workspace_auth import (workspace_access_allowed,
                                  workspace_client_allowed)

SERVER = ROOT / "backend" / "server.py"


def build_handler(token='a'*64, face_enabled=False):
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    handler = next(node for node in tree.body
                   if isinstance(node, ast.AsyncFunctionDef)
                   and node.name == "workspace_action")
    handler.decorator_list = []
    namespace = {
        "asyncio": asyncio,
        "sio": SimpleNamespace(emit=AsyncMock(),
                               get_environ=lambda sid: {"HTTP_ORIGIN": "http://localhost:5173"}),
        "workspace_client_allowed": workspace_client_allowed,
        "workspace_access_allowed": workspace_access_allowed,
        "os": SimpleNamespace(environ={"SPARK_WORKSPACE_TOKEN": token}),
        "audio_loop": None,  # no live voice session on this host
        "SETTINGS": {"face_auth_enabled": face_enabled},
        "authenticator": SimpleNamespace(authenticated=False),
        "spark_evolution": SimpleNamespace(execute=AsyncMock(return_value={})),
        "pc_tasks": SimpleNamespace(execute=AsyncMock(return_value={})),
        "spark_workspace": None,
        "workspace_project_by_sid": {},
        "EVOLUTION_ACTIONS": set(),
        "WorkspaceError": type("WorkspaceError", (Exception,), {}),
        "MaintenanceError": type("MaintenanceError", (Exception,), {}),
        "ReaError": type("ReaError", (Exception,), {}),
        "SkillError": type("SkillError", (Exception,), {}),
        "WORKBENCH_ACTIONS": WORKBENCH_ACTIONS,
        "WorkbenchError": WorkbenchError,
        "CAPABILITY_READ_ONLY_ACTIONS": CAPABILITY_READ_ONLY_ACTIONS,
        "FILE_ORGANIZER_ACTIONS": set(),
        "FILE_INTELLIGENCE_ACTIONS": set(),
        "file_organizer": None, "file_intelligence": None,
        "spark_workbench": SimpleNamespace(
            execute=AsyncMock(return_value={"sent": "back"})),
    }
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(SERVER), "exec"),
         namespace)
    return namespace


READ_ONLY = (
    "digest_status", "digest_run", "digest_history", "hub_status",
    "hub_history", "proactive_summary", "proactive_inbox", "opencode_status",
    "research_run", "trace_status", "trace_labeled", "learning_status",
    "spec_search_status", "spec_candidates", "skill_status", "skill_list",
    "skill_runs", "agents_status", "agents_runs", "monitor_status",
    "connector_status", "connector_freshness", "connector_events",
    "eval_status", "eval_history", "telemetry_status", "telemetry_report",
    "backend_describe", "backend_events",
)

MUTATING = (
    "hub_configure", "hub_disconnect", "hub_approve", "hub_send", "hub_receive",
    "proactive_propose", "proactive_decide", "proactive_execute",
    "proactive_undo", "opencode_run", "opencode_diff", "opencode_test",
    "digest_ack", "digest_speech", "digest_speak", "digest_configure",
    "trace_capture", "trace_label", "router_select", "learning_propose",
    "learning_activate", "learning_rollback", "spec_search_run",
    "spec_activate", "spec_rollback", "skill_import", "skill_review",
    "skill_run", "skill_revoke", "agents_react", "agents_codeact",
    "agents_recursive", "monitor_run", "monitor_cancel", "monitor_deliver",
    "monitor_acknowledge", "connector_attach_local", "connector_configure",
    "connector_validate", "connector_read", "connector_revoke",
    "eval_register", "eval_run", "eval_report", "eval_export",
    "telemetry_capture", "telemetry_record", "backend_probe",
    "backend_generate", "backend_opt_in",
)


class OfflineCockpitCapabilityGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_capability_action_belongs_to_the_workbench(self):
        for action in READ_ONLY + MUTATING:
            self.assertIn(action, WORKBENCH_ACTIONS)

    async def test_read_only_capability_actions_survive_voice_being_offline(self):
        namespace = build_handler()
        for action in READ_ONLY:
            with self.subTest(action=action):
                await namespace['workspace_action']('cockpit', {
                    'request_id': 'r1', 'action': action, 'project': 'general',
                    'workspace_token': 'a'*64, 'payload': {}})
                reply = namespace['sio'].emit.await_args.args[1]
                self.assertTrue(reply['ok'], msg=f"{action}: {reply.get('message')}")

    async def test_mutating_capability_actions_stay_owner_gated_offline(self):
        for action in MUTATING:
            with self.subTest(action=action):
                namespace = build_handler()
                await namespace['workspace_action']('cockpit', {
                    'request_id': 'r1', 'action': action, 'project': 'general',
                    'workspace_token': 'a'*64, 'payload': {}})
                reply = namespace['sio'].emit.await_args.args[1]
                self.assertFalse(reply['ok'], action)
                self.assertIn('Reconnect the Spark desktop workspace',
                              reply['message'], action)

    async def test_read_only_actions_also_require_the_workspace_token(self):
        for action in ("digest_status", "connector_status", "backend_describe"):
            with self.subTest(action=action):
                namespace = build_handler()
                await namespace['workspace_action']('stranger', {
                    'request_id': 'r2', 'action': action, 'project': 'general',
                    'workspace_token': None, 'payload': {}})
                reply = namespace['sio'].emit.await_args.args[1]
                self.assertFalse(reply['ok'], action)

    async def test_face_lock_blocks_read_only_capability_actions_too(self):
        for action in ("digest_status", "backend_describe"):
            with self.subTest(action=action):
                namespace = build_handler(face_enabled=True)
                await namespace['workspace_action']('cockpit', {
                    'request_id': 'r3', 'action': action, 'project': 'general',
                    'workspace_token': 'a'*64, 'payload': {}})
                reply = namespace['sio'].emit.await_args.args[1]
                self.assertFalse(reply['ok'], action)
                self.assertIn('face lock', reply['message'])
        # and unlocks with the authenticated face pass
        namespace = build_handler(face_enabled=True)
        namespace['authenticator'] = SimpleNamespace(authenticated=True)
        await namespace['workspace_action']('cockpit', {
            'request_id': 'r4', 'action': 'digest_status', 'project': 'general',
            'workspace_token': 'a'*64, 'payload': {}})
        self.assertTrue(namespace['sio'].emit.await_args.args[1]['ok'])


if __name__ == "__main__":
    unittest.main()
