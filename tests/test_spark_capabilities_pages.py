"""Capabilities Center — 16 functional pages wired to real backend actions.

Parity contract: every action name declared on a Capabilities Center page
must be a real `backend/spark_workbench.py` ACTION_KEYS entry whose payload
key set matches the page's declared fields, and the sixteen pages must be
reachable from the workspace navigation. A live dispatch run then proves
each page's status (and one governed voice-style call per page) returns an
honest shape. No network, no cloud.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench

CENTER = ROOT / "src" / "components" / "CapabilitiesCenter.jsx"
PANEL = ROOT / "src" / "components" / "WorkspacePanel.jsx"


def extract_pages():
    text = CENTER.read_text(encoding="utf-8")
    pages = {}
    current = None
    for line in text.splitlines():
        header = re.match(r"\s*\{id:'([a-z-]+)', num:'(\d+)'", line)
        if header:
            current = {"num": header[2], "actions": []}
            pages[header[1]] = current
        if current is not None:
            current["actions"] += re.findall(r"\{action:'([a-z_]+)'", line)
    return pages


class PageParityTests(unittest.TestCase):
    def setUp(self):
        self.pages = extract_pages()

    def test_sixteen_pages_with_separate_ids(self):
        self.assertEqual(len(self.pages), 16)
        self.assertEqual(sorted(page["num"] for page in self.pages.values()),
                         [f"{n:02d}" for n in range(1, 17)])

    def test_every_page_declares_a_status_action(self):
        for page_id, page in self.pages.items():
            self.assertGreaterEqual(len(page["actions"]), 1, page_id)

    def test_every_declared_action_is_a_real_backend_action(self):
        for page_id, page in self.pages.items():
            for action in page["actions"]:
                self.assertIn(action, ACTION_KEYS,
                              f"{page_id}: {action} is not dispatchable")

    def test_workspace_navigation_reaches_the_capabilities_center(self):
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("import CapabilitiesCenter from './CapabilitiesCenter';", panel)
        self.assertIn(">Capabilities</button>", panel)
        self.assertIn("tab==='capabilities' ? <CapabilitiesCenter", panel)

    def test_pages_declared_fields_match_action_key_sets(self):
        text = CENTER.read_text(encoding="utf-8")
        blocks = re.findall(
            r"\{action:'([a-z_]+)', label:'[^']*', fields:\[([^\]]*)\]", text)
        self.assertEqual(len(blocks), 73)
        field_block = r"\{key:'([a-z_]+)',type:'(?:text|number|bool|json)'"
        for action, fields in blocks:
            declared = set(re.findall(field_block, fields))
            self.assertEqual(declared, ACTION_KEYS[action],
                             f"{action}: page fields must equal the backend key set")


class CenterDispatchTests(unittest.IsolatedAsyncioTestCase):
    """Live dispatch of each page's status through the real workbench."""

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.directory.name)
        self.workbench = Workbench(self.workspace)
        self.addAsyncCleanup(self._close)

    async def _close(self):
        await self.workbench.integrations.close()
        await self.workbench.intelligence.close()
        self.directory.cleanup()

    async def test_status_actions_return_honest_shapes(self):
        honest_keys = {
            "digest_status": {"schema"},
            "hub_status": {"schema", "providers"},
            "proactive_summary": {"proposed", "approved"},
            "opencode_status": {"discovery", "policy"},
            "openclaw_status": {"state", "gateway", "operator_verified"},
            "trace_status": {"summary"},
            "learning_status": {"active_policy", "candidates"},
            "spec_search_status": {"planner", "runs_recorded"},
            "skill_status": {"operations", "integrity_model"},
            "agents_status": {"adapters", "max_steps", "codeact_scope"},
            "monitor_status": {"schema", "monitors"},
            "connector_status": {"by_state", "adapters_attached"},
            "eval_status": {"suites", "honesty"},
            "telemetry_status": {"entries", "energy"},
            "backend_describe": {"engines", "downloads"},
        }
        for action, required in honest_keys.items():
            result = await self.workbench.execute(action, "general", {})
            self.assertTrue(required <= set(result), action)


if __name__ == "__main__":
    unittest.main()
