from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


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
adapter = load_module("external_benchmark_dispatch_adapter", "external_benchmark_dispatch_adapter.py")
consolidation = load_module("academic_global_consolidation", "academic_global_consolidation.py")
runner = load_module("run_external_benchmark_certification", "run_external_benchmark_certification.py")
max_quality = load_module("run_academic_max_quality", "run_academic_max_quality.py")
route_beauty = load_module("run_route_beauty_benchmark", "run_route_beauty_benchmark.py")
elite = load_module("run_elite_food_dispatch_benchmark", "run_elite_food_dispatch_benchmark.py")


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

    def test_parse_official_li_lim_format(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/official/li-lim-pdptw/LC101.txt"))

        self.assertEqual("PDPTW", instance["problemType"])
        self.assertEqual(53, len(instance["requests"]))
        self.assertEqual(10, instance["bestKnown"]["vehicleCount"])
        self.assertEqual(828.94, instance["bestKnown"]["objective"])
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
            self.assertIn("instance-data-missing", row["verdictReasons"])

    def test_dispatch_adapter_preserves_benchmark_constraint_profile(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        dispatch_case = adapter.ExternalBenchmarkToDispatchCaseAdapter().adapt(instance)

        self.assertEqual("dispatch-v2-external-benchmark", dispatch_case.constraint_profile.mode)
        self.assertEqual("benchmark-matrix", dispatch_case.constraint_profile.distance_source)
        self.assertTrue(dispatch_case.constraint_profile.enforce_capacity)
        self.assertTrue(dispatch_case.constraint_profile.enforce_time_windows)
        self.assertTrue(dispatch_case.constraint_profile.enforce_pickup_before_dropoff)

    def test_runner_uses_dispatch_adapter_for_our_dispatch_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            row = runner.run_instance("solomon", "C101", "our-dispatch-v2", Path(temp_dir), 20.0, 30_000)

            self.assertEqual("external-benchmark-dispatch-adapter-v2", row["solverImplementation"])
            self.assertTrue(Path(row["solutionPath"]).exists())
    def test_runner_writes_report_for_smoke_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code = runner.main_args if hasattr(runner, "main_args") else None
            self.assertIsNone(code)
            row = runner.run_instance("solomon", "C101", "our-dispatch-v2", Path(temp_dir), 20.0, 30_000)

            self.assertIn(row["verdict"], {"PASS", "EVIDENCE_GAP"})
            if row["verdict"] == "PASS":
                self.assertTrue(Path(row["normalizedPath"]).exists())
            else:
                self.assertIn("ortools-python-unavailable", row["verdictReasons"][0])

    def test_verdict_high_gap_is_pass_with_limits(self) -> None:
        result = {"feasible": True, "objectiveGapPercent": 25.0}

        verdict, reasons = support.verdict(result, 20.0, 100, 30_000)

        self.assertEqual("PASS_WITH_LIMITS", verdict)
        self.assertIn("objective-gap-above-pass-threshold", reasons)

    def test_dispatch_adapter_records_vehicle_count_first_policy(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))

        solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 30_000, "our-dispatch-v2")

        self.assertEqual(["feasible", "vehicle-count", "distance"], solution["objectivePolicy"]["order"])
        self.assertEqual("academic-consolidation-enabled", solution["objectivePolicy"]["implementationStatus"])
        self.assertGreater(solution["objectivePolicy"]["vehicleFixedCost"], 0)

    def test_global_consolidator_eliminates_mergeable_route(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        instance["vehicleCount"] = 2
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "0"], ["0", "2", "3", "0"]]}

        result = consolidation.GlobalRouteConsolidator().consolidate(instance, solution)

        self.assertTrue(result.after_metrics["feasible"])
        self.assertEqual(1, result.after_metrics["vehicleCount"])
        self.assertEqual(1, result.trace.accepted_moves)

    def test_academic_max_quality_collects_valid_route_pool(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "3", "0"]]}
        evaluated = max_quality.evaluate_solution(instance, solution, "unit")

        pool = max_quality.collect_route_pool(instance, [evaluated])

        self.assertEqual(1, len(pool))
        self.assertTrue(pool[0]["capacityFeasible"])
        self.assertTrue(pool[0]["timeWindowFeasible"])
        self.assertEqual(["1", "2", "3"], pool[0]["customerSet"])

    def test_academic_max_quality_duration_parser_accepts_minutes(self) -> None:
        self.assertEqual(1_800_000, max_quality.parse_duration_ms("30m"))

    def test_academic_max_quality_has_no_case_specific_branching(self) -> None:
        source = Path("scripts/run_academic_max_quality.py").read_text(encoding="utf-8")

        forbidden_patterns = [
            "if instance_name ==",
            "if instance ==",
            ".startswith(\"R1_10_1\")",
            ".startswith('R1_10_1')",
            ".startswith(\"RC1_10_1\")",
            ".startswith('RC1_10_1')",
        ]
        for pattern in forbidden_patterns:
            self.assertNotIn(pattern, source)

    def test_route_beauty_metrics_detect_straight_route(self) -> None:
        coordinates = {1: (0.0, 0.0), 2: (1.0, 0.0), 3: (2.0, 0.0)}

        metrics = route_beauty.route_shape_metrics([1, 2, 3], coordinates, 2.0)

        self.assertTrue(metrics["routePolylinePresent"])
        self.assertEqual(0, metrics["turnCount"])
        self.assertAlmostEqual(1.0, metrics["straightnessScore"])

    def test_elite_scorecard_reports_missing_certification_as_evidence_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scorecard = elite.build_elite_scorecard(root / "missing", root / "missing-max", root / "missing-road")

        self.assertEqual("EVIDENCE_GAP", scorecard["finalVerdict"])
        self.assertEqual("systemReliability", scorecard["layers"][0]["layer"])


if __name__ == "__main__":
    unittest.main()
