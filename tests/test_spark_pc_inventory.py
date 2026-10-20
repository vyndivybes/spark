"""Tests for the section-5 Windows management-agent inventories (read-only)."""
import asyncio
import json
import subprocess
import tempfile
import unittest

from spark_evolution import Evolution, MaintenanceError
from spark_pc_inventory import (
    PcInventoryError, advisory, process_inventory, startup_inventory,
)
from spark_workspace import SparkWorkspace


class FakeKey:
    def __init__(self, values):
        self._values = list(values)

    def QueryInfoKey(self):
        return (len(self._values), 0)

    def EnumValue(self, index):
        return self._values[index]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeRegistry:
    KEY_READ = 0x20019
    KEY_WOW64_32KEY = 0x200
    HKEY_CURRENT_USER = 0x80000001
    HKEY_LOCAL_MACHINE = 0x80000002

    def __init__(self, tree):
        self._tree = tree

    def OpenKey(self, base, subkey, reserved, access):
        table = self._tree.get((base, access))
        if table is None or subkey not in table:
            raise OSError("missing")
        return FakeKey(table[subkey])

    def QueryInfoKey(self, key):
        return key.QueryInfoKey()

    def EnumValue(self, key, index):
        return key.EnumValue(index)


def fake_runner(payload_text):
    def runner(command):
        return payload_text
    return runner


class StartupTests(unittest.TestCase):
    def test_parses_registry_and_folders_merges_views(self):
        tree = {
            (FakeRegistry.HKEY_CURRENT_USER, FakeRegistry.KEY_READ): {
                "Software\\Microsoft\\Windows\\CurrentVersion\\Run": [
                    ("OneNote", "onenote.exe", 1),
                    ("", "empty name skipped", 1),
                ],
                "Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce": [
                    ("Updater", "update.exe /q", 1),
                ],
            },
            (FakeRegistry.HKEY_LOCAL_MACHINE, FakeRegistry.KEY_READ): {
                "Software\\Microsoft\\Windows\\CurrentVersion\\Run": [
                    ("Security", "defender.exe", 1),
                ],
            },
            (FakeRegistry.HKEY_LOCAL_MACHINE,
             FakeRegistry.KEY_READ | FakeRegistry.KEY_WOW64_32KEY): {
                "Software\\Microsoft\\Windows\\CurrentVersion\\Run": [
                    ("Legacy", "legacy.exe", 1),
                ],
            },
        }
        report = startup_inventory(
            registry=FakeRegistry(tree),
            user_startup=lambda: ["Slack.lnk", "ignore.txt"],
            common_startup=lambda: ["Teams.lnk"])
        names = [entry["name"] for entry in report["entries"]]
        self.assertEqual(
            names,
            ["OneNote", "Updater", "Security", "Legacy",
             "Slack.lnk", "ignore.txt", "Teams.lnk"])
        self.assertEqual(report["count"], 7)
        self.assertIn("HKLM:Run", [entry["source"] for entry in report["entries"]])
        self.assertIn("user-startup-folder",
                      [entry["source"] for entry in report["entries"]])

    def test_corrupt_values_and_caps_are_survivable(self):
        tree = {
            (FakeRegistry.HKEY_CURRENT_USER, FakeRegistry.KEY_READ): {
                "Software\\Microsoft\\Windows\\CurrentVersion\\Run": [
                    (12345, "not a name", 1),
                ],
            },
        }
        report = startup_inventory(
            registry=FakeRegistry(tree), user_startup=lambda: [],
            common_startup=lambda: [])
        self.assertEqual(report["entries"], [])
        self.assertIn("nothing is started", report["note"])

    def test_empty_machine_reports_zero_entries(self):
        report = startup_inventory(
            registry=FakeRegistry({}), user_startup=lambda: [],
            common_startup=lambda: [])
        self.assertEqual(report["count"], 0)
        self.assertEqual(report["truncated"], False)
        self.assertIn("nothing is started", report["note"])


class ProcessTests(unittest.TestCase):
    def sample(self):
        return [
            {"Id": 1, "ProcessName": "csrss", "CPU": 41.35,
             "WorkingSet64": 268435456, "Responding": True},
            {"Id": 2, "ProcessName": "chrome", "CPU": None,
             "WorkingSet64": None, "Responding": None},
            {"Id": 0, "ProcessName": "bad", "CPU": 0, "WorkingSet64": 0},
            {"Id": 3, "ProcessName": "codex", "CPU": 12.4,
             "WorkingSet64": 524288000, "Responding": False},
        ]

    def test_normalizes_list_snapshot(self):
        report = process_inventory(runner=fake_runner(json.dumps(self.sample())))
        self.assertEqual([item["name"] for item in report["processes"]],
                         ["codex", "csrss", "chrome"])
        self.assertEqual(report["processes"][0]["ram_mb"], 500.0)
        self.assertEqual(report["processes"][1]["cpu_seconds"], 41.4)
        self.assertIsNone(report["processes"][2]["ram_mb"])
        self.assertEqual(report["count"], 3)

    def test_single_object_snapshot_is_accepted(self):
        report = process_inventory(runner=fake_runner(
            json.dumps(self.sample()[0])))
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["processes"][0]["name"], "csrss")

    def test_bad_runner_and_json_raise_clean_errors(self):
        with self.assertRaises(PcInventoryError):
            process_inventory(runner=self._raising)
        with self.assertRaises(PcInventoryError):
            process_inventory(runner=fake_runner("<html>"))

    def _raising(self, command):
        raise subprocess.TimeoutExpired("powershell", 60)


class AdvisoryTests(unittest.TestCase):
    def findings(self, request):
        return [item["name"] for item in request["findings"]]

    def test_flags_ram_disk_heavy_and_startup(self):
        report = advisory(
            {"ram_percent": 94.0, "disk_free_gb": 8.2},
            [{"name": "App"}] * 14,
            [{"pid": 1, "name": "codex", "ram_mb": 900.0},
             {"pid": 2, "name": "csrss", "ram_mb": 600.0}])
        self.assertIn("ram", self.findings(report))
        self.assertIn("disk", self.findings(report))
        self.assertIn("startup", self.findings(report))
        heavy = [item for item in report["findings"]
                 if item["kind"] == "heavy_process"]
        self.assertEqual([(item["name"], item.get("safe_to_close"))
                          for item in heavy],
                         [("codex", True), ("csrss", False)])
        self.assertEqual(report["protected_count"], 1)
        self.assertIn("closes nothing", report["note"])

    def test_healthy_state_stays_quiet(self):
        report = advisory({"ram_percent": 42.0, "disk_free_gb": 120.0},
                          [{"name": "App"}] * 3,
                          [{"pid": 1, "name": "codex", "ram_mb": 120.0}])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["protected_count"], 0)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.temp.name)
        self.engine = Evolution(
            self.workspace,
            generator=lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("no model call")))

    def tearDown(self):
        self.temp.cleanup()

    def test_rejects_unknown_payload_keys(self):
        with self.assertRaises(MaintenanceError):
            asyncio.run(self.engine.execute(
                "pc_startup_inventory", "general", {"force": True}))

    def test_real_startup_inventory_reports_entries(self):
        report = asyncio.run(self.engine.execute(
            "pc_startup_inventory", "general", {}))
        self.assertIn("entries", report)
        self.assertIn("note", report)
        self.assertEqual(report["count"], len(report["entries"]))


if __name__ == "__main__":
    unittest.main()
