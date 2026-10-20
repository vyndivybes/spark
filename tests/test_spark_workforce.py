import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workforce import (
    FORBIDDEN_INNER,
    ROLES,
    WorkforceError,
    check_assignment,
    roles_summary,
)


class RegistryTests(unittest.TestCase):
    def test_core_roles_present(self):
        expected = {"planner", "researcher", "architect", "developer", "tester",
                    "security_auditor", "repair_agent", "performance_engineer",
                    "system_monitor", "release_manager"}
        self.assertTrue(expected <= set(ROLES))

    def test_every_role_has_actions_and_name(self):
        for role_id, spec in ROLES.items():
            with self.subTest(role=role_id):
                self.assertTrue(spec["actions"], "empty allowlist")
                self.assertTrue(spec["name"])
                self.assertTrue(spec["responsibility"])

    def test_summary_lists_all_roles(self):
        summary = roles_summary()
        self.assertEqual({item["id"] for item in summary}, set(ROLES))
        self.assertTrue(all(item["actions"] for item in summary))


class AssignmentTests(unittest.TestCase):
    def test_scoped_action_passes_through_unchanged(self):
        action, payload = check_assignment("security_auditor", "security_scan",
                                           {"paths": ["backend/ok.py"]})
        self.assertEqual((action, payload), ("security_scan", {"paths": ["backend/ok.py"]}))

    def test_unknown_role_refused(self):
        with self.assertRaises(WorkforceError):
            check_assignment("ghost", "disk_forecast", {})

    def test_out_of_scope_action_refused(self):
        with self.assertRaises(WorkforceError):
            check_assignment("planner", "heal_sources", {})
        with self.assertRaises(WorkforceError):
            check_assignment("tester", "activate_repair_candidate", {})

    def test_non_dict_payload_refused(self):
        with self.assertRaises(WorkforceError):
            check_assignment("planner", "saee_discover", None)

    def test_self_approval_refused(self):
        with self.assertRaises(WorkforceError):
            check_assignment("tester", "test_repair_candidate", {"id": "x", "approved": True})
        # False is allowed: routing still requires the trusted route later.
        check_assignment("tester", "test_repair_candidate", {"id": "x", "approved": False})

    def test_nested_assignments_refused(self):
        for action in FORBIDDEN_INNER:
            with self.subTest(action=action):
                with self.assertRaises(WorkforceError):
                    check_assignment("planner", action, {})

    def test_forbidden_set_holds_meta_actions(self):
        self.assertIn("workforce_assign", FORBIDDEN_INNER)
        self.assertIn("workforce_roles", FORBIDDEN_INNER)


if __name__ == "__main__":
    unittest.main()
