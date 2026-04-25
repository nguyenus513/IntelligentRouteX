from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_module(name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


support = load_module("external_benchmark_support", "external_benchmark_support.py")
solomon = load_module("parse_solomon_vrptw", "parse_solomon_vrptw.py")
li_lim = load_module("parse_li_lim_pdptw", "parse_li_lim_pdptw.py")
runner = load_module("run_external_benchmark_certification", "run_external_benchmark_certification.py")


class ExternalBenchmarkCertificationTest(unittest.TestCase):
    def test_parse_solomon_fixture(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))

        self.assertEqual("solomon", instance["benchmarkFamily"])
        self.assertEqual("VRPTW", instance["problemType"])
        self.assertEqual(4, len(instance["nodes"]))
        self.assertEqual(60.0, instance["bestKnown"]["objective"])

    def test_parse_li_lim_fixture_keeps_pickup_dropoff_pairs(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))

        self.assertEqual("li-lim", instance["benchmarkFamily"])
        self.assertEqual("PDPTW", instance["problemType"])
        self.assertEqual(2, len(instance["requests"]))
        self.assertEqual("1", instance["requests"][0]["pickupNodeId"])
        self.assertEqual("2", instance["requests"][0]["dropoffNodeId"])

    def test_checker_detects_pickup_dropoff_violation(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        solution = {"routes": [["0", "2", "1", "3", "4", "0"]]}

        checked = support.check_solution(instance, solution)

        self.assertFalse(checked["feasible"])
        self.assertGreater(checked["pickupBeforeDropoffViolationCount"], 0)

    def test_checker_detects_capacity_violation(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        instance["capacity"] = 1
        solution = {"routes": [["0", "1", "3", "2", "4", "0"]]}

        checked = support.check_solution(instance, solution)

        self.assertFalse(checked["feasible"])
        self.assertGreater(checked["capacityViolationCount"], 0)

    def test_checker_detects_time_window_violation(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        instance["nodes"][1]["dueTime"] = 5
        solution = {"routes": [["0", "1", "2", "3", "0"]]}

        checked = support.check_solution(instance, solution)

        self.assertFalse(checked["feasible"])
        self.assertGreater(checked["timeWindowViolationCount"], 0)

    def test_checker_detects_route_not_ending_at_depot(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        solution = {"routes": [["0", "1", "2", "3"]]}

        checked = support.check_solution(instance, solution)

        self.assertFalse(checked["feasible"])
        self.assertIn("route-does-not-start-end-at-depot", checked["violations"])

    def test_checker_detects_unknown_route_node(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        solution = {"routes": [["0", "1", "999", "0"]]}

        checked = support.check_solution(instance, solution)

        self.assertFalse(checked["feasible"])
        self.assertIn("unknown-node-in-route", checked["violations"])

    def test_parser_rejects_malformed_solomon_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            malformed = Path(temp_dir) / "bad.txt"
            malformed.write_text("BAD\nVEHICLE\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                solomon.parse_solomon(malformed)

    def test_runner_reports_missing_fixture_as_evidence_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            row = runner.run_instance("solomon", "MISSING", "our-dispatch-v2", Path(temp_dir), 20.0, 30_000)

            self.assertEqual("EVIDENCE_GAP", row["verdict"])
            self.assertIn("instance-fixture-missing", row["verdictReasons"])

    def test_runner_writes_report_for_smoke_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code = runner.main_args if hasattr(runner, "main_args") else None
            self.assertIsNone(code)
            row = runner.run_instance("solomon", "C101", "our-dispatch-v2", Path(temp_dir), 20.0, 30_000)

            self.assertEqual("PASS", row["verdict"])
            self.assertTrue(Path(row["normalizedPath"]).exists())

    def test_verdict_high_gap_is_pass_with_limits(self) -> None:
        result = {"feasible": True, "objectiveGapPercent": 25.0}

        verdict, reasons = support.verdict(result, 20.0, 100, 30_000)

        self.assertEqual("PASS_WITH_LIMITS", verdict)
        self.assertIn("objective-gap-above-pass-threshold", reasons)


if __name__ == "__main__":
    unittest.main()
