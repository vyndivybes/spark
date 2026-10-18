"""First source-independent parity feature: read-only Windows hardware vitals.

This code is NOT copied from Brahma's non-redistributable implementation.
Tests show no device paths, process names, or secrets cross the SPARK socket.
"""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from spark_host_vitals import (
    normalize_host_vitals, collect_host_vitals, calculate_cpu_busy, EMPTY_VITALS
)
from spark_diagnostics import safe_diagnostics

class WindowsVitalsTests(unittest.TestCase):
    def test_read_only_values_have_strict_keys_and_bounded_precision(self):
        raw={
            "cpu_percent":33.339, "ram_percent":55.619,
            "ram_total_gb":16.09,"ram_available_gb":7.04,
            "disk_total_gb":237.51,"disk_free_gb":50.128,
            "battery_percent":87.77,"ac_connected":True,
            "secret_path":"C:\\Users\\ASUS\\secrets.json",
            "api_key":"DO_NOT_LEAK","pids":[1234]
        }
        result=collect_host_vitals(sampler=lambda:raw)
        self.assertEqual(result["cpu_percent"],33.3)
        self.assertEqual(result["ram_percent"],55.6)
        self.assertEqual(result["disk_free_gb"],50.13)
        self.assertEqual(result["battery_percent"],87.8)
        self.assertTrue(result["ac_connected"])
        self.assertEqual(set(result), set(EMPTY_VITALS))
        report=safe_diagnostics({"ai_provider":"groq","host":result})
        self.assertEqual(report["host"],result)
        self.assertNotIn("DO_NOT_LEAK",str(report))
        self.assertNotIn("ASUS",str(report))
        self.assertNotIn("pids",str(report))

    def test_invalid_and_absent_values_are_unknown_not_fabricated(self):
        raw={"cpu_percent":float("nan"),"ram_percent":-8,
             "ram_total_gb":float("inf"),"disk_free_gb":-1,
             "battery_percent":255,"ac_connected":"yes"}
        result=normalize_host_vitals(raw)
        self.assertTrue(all(x is None for x in result.values()))
        self.assertEqual(collect_host_vitals(platform_name="posix"),EMPTY_VITALS)
        self.assertEqual(collect_host_vitals(sampler=lambda: (_ for _ in ()).throw(OSError())),EMPTY_VITALS)

    def test_cpu_percentage_uses_positive_monotonic_windows_ticks(self):
        # get_system_times triples: idle, kernel (includes idle), user
        self.assertEqual(calculate_cpu_busy((30,50,50),(40,70,70)),75.0)
        self.assertIsNone(calculate_cpu_busy((100,300,200),(90,350,250)))
        self.assertIsNone(calculate_cpu_busy((0,5,5),(0,5,5)))

    def test_normalization_cannot_reflect_invalid_report_objects(self):
        report=safe_diagnostics({"host":{"cpu_percent":35,"ram_percent":"not-a-number",
                    "disk_total_gb":"C:/Users/ASUS","unknown":"SECRET"}})
        self.assertEqual(report["host"]["cpu_percent"],35.0)
        self.assertIsNone(report["host"]["ram_percent"])
        self.assertNotIn("SECRET",str(report))

if __name__=="__main__":unittest.main()
