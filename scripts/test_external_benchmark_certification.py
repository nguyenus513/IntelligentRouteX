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
route_condition = load_module("run_route_condition_benchmark", "run_route_condition_benchmark.py")
traffic_route = load_module("run_community_traffic_route_benchmark", "run_community_traffic_route_benchmark.py")
weather_route = load_module("run_community_weather_route_benchmark", "run_community_weather_route_benchmark.py")
gap_plan = load_module("build_elite_gap_closure_plan", "build_elite_gap_closure_plan.py")
closure_loop = load_module("run_elite_closure_loop", "run_elite_closure_loop.py")
food_quality = load_module("run_food_dispatch_quality_benchmark", "run_food_dispatch_quality_benchmark.py")
dynamic_quality = load_module("run_dynamic_dispatch_quality_benchmark", "run_dynamic_dispatch_quality_benchmark.py")
stochastic_data = load_module("download_stochastic_benchmark_data", "download_stochastic_benchmark_data.py")
stochastic_benchmark = load_module("run_stochastic_community_benchmark", "run_stochastic_community_benchmark.py")
ml_quality = load_module("run_ml_intelligence_benchmark", "run_ml_intelligence_benchmark.py")


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

    def test_academic_max_quality_generates_route_merge_candidates(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        route_pool = []
        seed = {"routes": [["0", "1", "0"], ["0", "2", "3", "0"]]}

        counts = max_quality.generate_route_merge_candidates(instance, seed, route_pool, max_pairs=4, max_combined_customers=4)

        self.assertGreaterEqual(counts["routeMergeAttempts"], 1)
        self.assertGreaterEqual(counts["routeMergeGeneratedRoutes"], 1)
        self.assertTrue(any(route["sourceRun"] == "route-merge-v5" for route in route_pool))

    def test_route_beauty_metrics_detect_straight_route(self) -> None:
        coordinates = {1: (0.0, 0.0), 2: (1.0, 0.0), 3: (2.0, 0.0)}

        metrics = route_beauty.route_shape_metrics([1, 2, 3], coordinates, 2.0)

        self.assertTrue(metrics["routePolylinePresent"])
        self.assertEqual(0, metrics["turnCount"])
        self.assertAlmostEqual(1.0, metrics["straightnessScore"])

    def test_route_beauty_classifies_bad_shape(self) -> None:
        row = {"straightnessScore": 0.20, "networkDetourRatio": 5.0}

        classified = route_beauty.classify_route_shape(row)

        self.assertEqual("high-detour-and-low-straightness", classified["routeShapeIssue"])
        self.assertEqual("topology-constrained", classified["routeShapeIssueClass"])

    def test_elite_scorecard_reports_missing_certification_as_evidence_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scorecard = elite.build_elite_scorecard(root / "missing", root / "missing-max", root / "missing-road")

        self.assertEqual("EVIDENCE_GAP", scorecard["finalVerdict"])
        self.assertEqual("systemReliability", scorecard["layers"][0]["layer"])

    def test_elite_scorecard_builds_action_plan_from_blockers(self) -> None:
        plan = elite.build_action_plan(["vehicle-count-gap", "rl4co-not-integrated"])

        self.assertEqual("rl4co-not-integrated", plan[0]["blocker"])
        self.assertIn("RL4CO", plan[0]["recommendedAction"])

    def test_route_condition_edge_factor_increases_cost(self) -> None:
        factor = route_condition.edge_factor(1, 2, route_condition.PROFILES["storm-peak"])

        self.assertGreater(factor, 1.0)

    def test_community_traffic_benchmark_reports_missing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            row = traffic_route.evaluate_dataset(Path(temp_dir), "metr-la", 2)

        self.assertEqual("EVIDENCE_GAP", row["verdict"])
        self.assertIn("community-traffic-data-missing", row["verdictReasons"])

    def test_elite_traffic_score_does_not_block_unavoidable_peak_stress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = {"finalVerdict": "PASS", "datasets": [{"dataset": "unit", "routeCount": 2, "badTrafficRouteCount": 0, "unavoidablePeakStressRouteCount": 2, "avgPeakVsOffPeakRatio": 3.0}]}
            path = root / "traffic_route_results.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            layer = elite.score_community_traffic_route(root)

        self.assertEqual([], layer["blockers"])
        self.assertEqual(2, layer["metrics"]["unavoidablePeakStressRouteCount"])

    def test_community_weather_benchmark_reports_missing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            row = weather_route.evaluate_dataset(root / "missing-road", root / "missing-weather", "open-meteo-ny", ["NY"], 2, 1, 100)

        self.assertEqual("EVIDENCE_GAP", row["verdict"])
        self.assertIn("community-weather-data-missing", row["verdictReasons"])

    def test_community_weather_edge_factor_increases_cost(self) -> None:
        event = {"rainMm": 5.0, "precipitationMm": 5.0, "windKmh": 35.0, "severity": 0.75}

        factor = weather_route.edge_weather_factor(1, 2, event)

        self.assertGreater(factor, 1.0)

    def test_elite_gap_closure_plan_prioritizes_academic_quality(self) -> None:
        scorecard = {
            "finalVerdict": "PASS_WITH_LIMITS",
            "overallScore": 0.85,
            "mainBlockers": ["ml-value-not-proven", "vehicle-count-gap", "route-beauty-limits"],
            "layers": [
                {"layer": "academicRoutingQuality", "blockers": ["vehicle-count-gap"]},
                {"layer": "mlIntelligence", "blockers": ["ml-value-not-proven"]},
                {"layer": "roadRouteBeauty", "blockers": ["route-beauty-limits"]},
            ],
        }

        plan = gap_plan.build_plan(scorecard)

        self.assertEqual("academic-max-quality-v5", plan["nextRail"])
        self.assertEqual([], plan["uncoveredBlockers"])

    def test_elite_closure_loop_defines_eight_phases(self) -> None:
        loop_phases = closure_loop.phases("smoke", Path("artifacts/benchmark/test-loop"))

        self.assertEqual(8, len(loop_phases))
        self.assertEqual("academic-max-quality-v5", loop_phases[0].phase)
        self.assertEqual("elite-scorecard-and-gap-plan", loop_phases[-1].phase)

    def test_food_quality_layer_replaces_proxy_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = {
                "layers": [
                    {"layer": "anchorQuality", "score": 0.95, "verdict": "PASS", "blockers": [], "metrics": {"avgPickupWaitTime": 1.0}}
                ]
            }
            food_path = root / "food" / "food_dispatch_quality_results.json"
            food_path.parent.mkdir(parents=True)
            food_path.write_text(json.dumps(payload), encoding="utf-8")

            layer = elite.score_anchor_quality([], root / "food")

        self.assertEqual("anchorQuality", layer["layer"])
        self.assertEqual([], layer["blockers"])

    def test_food_quality_scores_mdrp_rows(self) -> None:
        rows = [{
            "servedOrderCount": 10,
            "orderCount": 10,
            "lateOrderRate": 0.0,
            "p95Delay": 5.0,
            "p95FoodOnVehicleTime": 6.0,
            "pickupBeforeReadyTimeViolation": 0,
            "courierShiftViolation": 0,
            "foodOnVehicleHardViolation": 0,
        }]

        layer = food_quality.score_food(rows)

        self.assertEqual("PASS", layer["verdict"])

    def test_food_quality_explainability_ranks_worst_instances(self) -> None:
        rows = [{"instanceName": "easy", "p95Delay": 3.0}, {"instanceName": "hard", "p95Delay": 9.0}]

        ranked = food_quality.top_instances(rows, "p95Delay", limit=1)

        self.assertEqual("hard", ranked[0]["instance"])

    def test_dynamic_quality_uses_certification_baseline_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cert = root / "cert" / "certification_suite_results.json"
            cert.parent.mkdir(parents=True)
            cert.write_text(json.dumps({"results": [{"suite": "icaps-dpdp", "instance": "unit", "solver": "deterministic-rolling-horizon-baseline", "verdict": "PASS_WITH_LIMITS", "orderCount": 10, "servedOrderCount": 10, "totalTardiness": 0.0, "activeRouteCorruptionCount": 0, "vehicleStateContinuityViolation": 0, "routeStabilityScore": 1.0}]}), encoding="utf-8")

            result = dynamic_quality.build_quality(root / "cert")

        self.assertEqual("PASS", result["finalVerdict"])
        self.assertTrue(result["baselineComparisonAvailable"])

    def test_stochastic_manifest_is_evidence_gap_without_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = stochastic_data.build_manifest(Path(temp_dir), download=False)
            stochastic_data.write_json(Path(temp_dir) / "manifest.json", manifest)
            result = stochastic_benchmark.build_result(Path(temp_dir))

        self.assertEqual("EVIDENCE_GAP", result["finalVerdict"])
        self.assertIn("public-stochastic-vrp-data-missing", result["verdictReasons"])

    def test_ml_value_evidence_uses_ablation_rows(self) -> None:
        rows = [
            {"component": "routefinder", "robustUtilityDelta": 0.1, "selectorObjectiveDelta": 0.0},
            {"component": "forecast", "robustUtilityDelta": 0.0, "selectorObjectiveDelta": 0.2},
        ]

        evidence = ml_quality.ml_value_evidence(rows)

        self.assertTrue(evidence["mlValueProven"])

    def test_baseline_competitiveness_reports_root_cause(self) -> None:
        rows = [{"stage": "A-academic-correctness", "suite": "solomon", "instance": "R101", "verdict": "PASS_WITH_LIMITS", "vehicleCount": 20, "bestKnownVehicleCount": 19}]

        with tempfile.TemporaryDirectory() as temp_dir:
            layer = elite.score_baseline_competitiveness(rows, Path(temp_dir) / "max", Path(temp_dir) / "pyvrp")

        self.assertEqual("vehicle-count", layer["metrics"]["strongBaselineGapRootCause"])


if __name__ == "__main__":
    unittest.main()
