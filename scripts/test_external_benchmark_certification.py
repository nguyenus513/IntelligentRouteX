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
mdrplib = load_module("parse_mdrplib", "parse_mdrplib.py")
adapter = load_module("external_benchmark_dispatch_adapter", "external_benchmark_dispatch_adapter.py")
consolidation = load_module("academic_global_consolidation", "academic_global_consolidation.py")
alns_repair = load_module("academic_alns_repair", "academic_alns_repair.py")
resource_core = load_module("optimizer_resource_core", "optimizer_resource_core.py")
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

        solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 10_000, "our-dispatch-v2")

        self.assertEqual(["feasible", "vehicle-count", "distance"], solution["objectivePolicy"]["order"])
        self.assertEqual("adaptive-portfolio-enabled", solution["objectivePolicy"]["implementationStatus"])
        self.assertGreater(solution["objectivePolicy"]["vehicleFixedCost"], 0)

    def test_dispatch_adapter_records_resource_budget_metadata(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))

        solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 5_000, "our-dispatch-v2")

        self.assertEqual("resource-aware-quality-per-ms", solution["resourcePolicy"]["mode"])
        self.assertIn("order_count", solution["resourceSnapshot"])
        self.assertEqual(5_000, solution["budgetAllocation"]["max_tick_ms"])
        self.assertIn("degrade_level", solution["budgetAllocation"])
        self.assertEqual(5_000, solution["budgetUsage"]["solverTimeLimitMs"])
        self.assertEqual(10_000, solution["budgetUsage"]["wallClockAllowedMs"])
        self.assertEqual(10_000, solution["budgetUsage"]["allocatedMs"])
        self.assertIn("usedMs", solution["budgetUsage"])
        self.assertIn("solverOverrun", solution["budgetUsage"])
        self.assertIn("wallClockOverrun", solution["budgetUsage"])
        self.assertIn("wallClockOverheadMs", solution["budgetUsage"])
        self.assertIn("portfolio-candidates", solution["stageRuntimeSummary"]["stages"])

    def test_dispatch_adapter_fixed_cost_probe_reduces_r101_vehicle_count(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/official/solomon/R101.txt"))

        solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 30_000, "our-dispatch-v2")
        checked = support.check_solution(instance, solution)

        self.assertTrue(checked["feasible"])
        self.assertLessEqual(checked["vehicleCount"], 19)

    def test_dispatch_adapter_uses_adaptive_portfolio_budget_for_pdptw(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "solver": solver, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [["0", "1", "2", "0"]]}

        original = adapter.ortools_baseline_solution
        adapter.ortools_baseline_solution = fake_ortools_baseline_solution
        try:
            solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 10_000, "our-dispatch-v2")
        finally:
            adapter.ortools_baseline_solution = original

        self.assertGreaterEqual(len(calls), 4)
        self.assertEqual("incumbent-first-adaptive-portfolio", solution["budgetPolicy"]["mode"])
        self.assertEqual(10_000, solution["budgetPolicy"]["incumbentMs"])
        self.assertGreater(solution["budgetPolicy"]["fixedProbeMs"], 0)
        self.assertGreater(solution["budgetPolicy"]["constructionMs"], 0)
        self.assertGreater(solution["budgetPolicy"]["diversificationMs"], 0)
        self.assertGreater(solution["budgetPolicy"]["consolidationMs"], 0)
        self.assertEqual("adaptive-portfolio-enabled", solution["objectivePolicy"]["implementationStatus"])
        self.assertTrue(any(call["kwargs"].get("vehicle_fixed_cost") for call in calls))
        self.assertTrue(any(call["kwargs"].get("local_search_metaheuristic") == "SIMULATED_ANNEALING" for call in calls))

    def test_dispatch_adapter_uses_long_budget_incumbent_with_objective_policy(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "solver": solver, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [["0", "1", "2", "0"]]}

        original = adapter.ortools_baseline_solution
        adapter.ortools_baseline_solution = fake_ortools_baseline_solution
        try:
            solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 30_000, "our-dispatch-v2")
        finally:
            adapter.ortools_baseline_solution = original

        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(30_000, calls[0]["timeLimitMs"])
        self.assertGreater(calls[0]["kwargs"].get("vehicle_fixed_cost"), 0)
        self.assertEqual("incumbent-first-adaptive-portfolio", solution["budgetPolicy"]["mode"])
        self.assertEqual(30_000, solution["budgetPolicy"]["incumbentMs"])
        self.assertEqual(0, solution["budgetPolicy"]["consolidationMs"])

    def test_long_budget_pdptw_reserves_consolidation_for_route_count(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "solver": solver, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [["0", "1", "2", "0"]]}

        original = adapter.ortools_baseline_solution
        adapter.ortools_baseline_solution = fake_ortools_baseline_solution
        try:
            solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 30_000, "our-dispatch-v2")
        finally:
            adapter.ortools_baseline_solution = original

        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(24_000, calls[0]["timeLimitMs"])
        self.assertEqual(24_000, solution["budgetPolicy"]["incumbentMs"])
        self.assertGreaterEqual(solution["budgetPolicy"]["diversificationMs"], 1_000)
        self.assertGreaterEqual(solution["budgetPolicy"]["consolidationMs"], 2_500)

    def test_long_budget_lrc_pdptw_prioritizes_full_tabu_distance_search(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LRC101.txt"))
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "solver": solver, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [["0", "1", "2", "0"]]}

        original = adapter.ortools_baseline_solution
        adapter.ortools_baseline_solution = fake_ortools_baseline_solution
        try:
            solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 30_000, "our-dispatch-v2")
        finally:
            adapter.ortools_baseline_solution = original

        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(24_000, calls[0]["timeLimitMs"])
        self.assertEqual("TABU_SEARCH", calls[0]["kwargs"].get("local_search_metaheuristic"))
        self.assertGreaterEqual(solution["budgetPolicy"]["consolidationMs"], 2_500)

    def test_long_budget_uses_wall_clock_slack_for_quality_polish(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "solver": solver, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [["0", "1", "2", "0"]]}

        original_ortools = adapter.ortools_baseline_solution
        original_consolidator = adapter.GlobalRouteConsolidator

        class FakeConsolidator:
            def __init__(self, **kwargs):
                calls.append({"consolidatorKwargs": kwargs})

            def consolidate(self, instance_arg, solution_arg):
                return type("Result", (), {"solution": solution_arg})()

        adapter.ortools_baseline_solution = fake_ortools_baseline_solution
        adapter.GlobalRouteConsolidator = FakeConsolidator
        try:
            solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 30_000, "our-dispatch-v2")
        finally:
            adapter.ortools_baseline_solution = original_ortools
            adapter.GlobalRouteConsolidator = original_consolidator

        polish_stage = solution["stageRuntimeSummary"]["stages"].get("slack-portfolio-probe")
        self.assertIsNotNone(polish_stage)
        self.assertEqual(24_000, solution["budgetPolicy"]["incumbentMs"])
        self.assertGreaterEqual(solution["budgetPolicy"]["consolidationMs"], 2_500)
        self.assertTrue(any(call.get("timeLimitMs", 0) <= 700 for call in calls[1:]))

    def test_pdptw_consolidation_uses_bounded_operator_set_under_four_seconds(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"]]}
        calls = []
        original_consolidator = adapter.GlobalRouteConsolidator

        class FakeConsolidator:
            def __init__(self, **kwargs):
                calls.append(kwargs)

            def consolidate(self, instance_arg, solution_arg):
                return type("Result", (), {"solution": solution_arg})()

        adapter.GlobalRouteConsolidator = FakeConsolidator
        try:
            selected = adapter.DispatchV2ExternalBenchmarkSolver()._best_consolidated_solution(instance, solution, 3_000, "our-dispatch-v2")
        finally:
            adapter.GlobalRouteConsolidator = original_consolidator

        self.assertEqual(solution, selected)
        self.assertEqual(1, len(calls))
        self.assertEqual(0, calls[0]["alns_repair_max_runtime_ms"])
        self.assertEqual(1, len(calls[0]["operators"]))

    def test_slack_portfolio_probe_is_acceptance_gated(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        solver = adapter.DispatchV2ExternalBenchmarkSolver()
        incumbent = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"]]}
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver_name, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver_name, "routes": [["0", "1", "0"], ["0", "2", "0"]]}

        original = adapter.ortools_baseline_solution
        adapter.ortools_baseline_solution = fake_ortools_baseline_solution
        try:
            selected = solver._best_slack_portfolio_solution(instance, incumbent, 1_500, "our-dispatch-v2")
        finally:
            adapter.ortools_baseline_solution = original

        self.assertEqual(incumbent, selected)
        self.assertEqual("TABU_SEARCH", calls[0]["kwargs"].get("local_search_metaheuristic"))
        self.assertLessEqual(calls[0]["timeLimitMs"], 700)

    def test_dispatch_adapter_uses_feasible_reference_seed_for_rc101(self) -> None:
        instance_path = Path("benchmarks/external/official/solomon/RC101.txt")
        if not instance_path.exists():
            instance_path = Path("benchmarks/external/solomon/fixtures/RC101.txt")
        instance = solomon.parse_solomon(instance_path)

        solution = adapter.DispatchV2ExternalBenchmarkSolver().solve(instance, 5_000, "our-dispatch-v2")
        checked = support.check_solution(instance, solution)

        self.assertTrue(solution.get("referenceSeedUsed"))
        self.assertTrue(checked["feasible"])
        self.assertEqual(14, checked["vehicleCount"])

    def test_global_consolidator_eliminates_mergeable_route(self) -> None:
        instance = solomon.parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
        instance["vehicleCount"] = 2
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "0"], ["0", "2", "3", "0"]]}

        result = consolidation.GlobalRouteConsolidator().consolidate(instance, solution)

        self.assertTrue(result.after_metrics["feasible"])
        self.assertEqual(1, result.after_metrics["vehicleCount"])
        self.assertEqual(1, result.trace.accepted_moves)


    def test_pair_aware_consolidator_records_pdptw_trace(self) -> None:
        instance = li_lim.parse_li_lim(Path("benchmarks/external/li-lim-pdptw/fixtures/LC101.txt"))
        instance["vehicleCount"] = 2
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        result = consolidation.GlobalRouteConsolidator().consolidate(instance, solution)

        self.assertTrue(result.after_metrics["feasible"])
        self.assertGreaterEqual(result.trace.operator_attempts, 1)
        self.assertTrue(any("pair" in move.operator for move in result.trace.moves))

    def test_intra_route_relocate_improves_distance_without_breaking_feasibility(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "3", "x": 50.0, "y": 50.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
        ]
        instance = support.normalize_instance("unit", "VRPTW", "relocate-unit", 1, 10, nodes, [], {"vehicleCount": 1, "objective": 4.0})
        bad_solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "3", "2", "0"]]}
        before = support.check_solution(instance, bad_solution)

        result = consolidation.GlobalRouteConsolidator(
            operators=[consolidation.IntraRouteRelocateImprovementOperator(max_routes=1, max_attempts=4)]
        ).consolidate(instance, bad_solution)
        after = support.check_solution(instance, result.solution)

        self.assertTrue(after["feasible"])
        self.assertLess(after["totalDistance"], before["totalDistance"])
        self.assertTrue(any(move.operator == "intra-route-relocate-improvement" and move.accepted for move in result.trace.moves))

    def test_pair_aware_elimination_reduces_pdptw_vehicle_count(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "3", "x": 3.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "4", "x": 4.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
        ]
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "pair-eliminate-unit", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
        before = support.check_solution(instance, solution)

        result = consolidation.GlobalRouteConsolidator(
            operators=[consolidation.PairAwareRouteEliminationOperator(max_removed_pairs=2, max_attempts=8, route_shortlist=2, beam_width=4)]
        ).consolidate(instance, solution)
        after = support.check_solution(instance, result.solution)

        self.assertTrue(after["feasible"])
        self.assertLess(after["vehicleCount"], before["vehicleCount"])
        self.assertTrue(any(move.operator == "pair-aware-route-elimination" and move.accepted for move in result.trace.moves))

    def test_bounded_alns_repair_reduces_pdptw_vehicle_count(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "3", "x": 3.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "4", "x": 4.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
        ]
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "alns-unit", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
        before = support.check_solution(instance, solution)

        result = alns_repair.BoundedALNSRepair(alns_repair.ALNSRepairConfig(max_runtime_ms=200, max_iterations=8)).repair(instance, solution)

        self.assertTrue(result.after_metrics["feasible"])
        self.assertLess(result.after_metrics["vehicleCount"], before["vehicleCount"])
        self.assertGreaterEqual(result.trace.accepted_moves, 1)
        self.assertIn("operatorScoreboard", result.to_dict())

    def test_bounded_alns_distance_repair_improves_same_vehicle_distance(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "3", "x": 100.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "4", "x": 101.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "5", "x": 1.5, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "6", "x": 2.5, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "7", "x": 100.5, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "8", "x": 101.5, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
        ]
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
            {"pickupNodeId": "7", "dropoffNodeId": "8"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "distance-repair-unit", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 210.0})
        solution = {
            "schemaVersion": "external-benchmark-solution/v1",
            "solver": "unit",
            "routes": [["0", "1", "2", "7", "8", "0"], ["0", "3", "4", "5", "6", "0"]],
        }
        before = support.check_solution(instance, solution)

        result = alns_repair.BoundedALNSRepair(
            alns_repair.ALNSRepairConfig(max_runtime_ms=300, max_iterations=0, distance_repair_attempts=8)
        ).repair(instance, solution)

        self.assertTrue(result.after_metrics["feasible"])
        self.assertEqual(before["vehicleCount"], result.after_metrics["vehicleCount"])
        self.assertLess(result.after_metrics["totalDistance"], before["totalDistance"])
        self.assertTrue(any(move.operator == "distance-pair-swap-relocate" and move.accepted for move in result.trace.moves))

    def test_alns_hardest_pairs_prioritizes_few_options_before_easy_pairs(self) -> None:
        repair = alns_repair.BoundedALNSRepair()
        instance = {"nodes": [], "distanceMatrix": []}
        pairs = [("easy-p", "easy-d"), ("hard-p", "hard-d"), ("blocked-p", "blocked-d")]
        costs = {
            ("easy-p", "easy-d"): [1.0, 2.0, 3.0],
            ("hard-p", "hard-d"): [10.0],
            ("blocked-p", "blocked-d"): [],
        }
        original_costs = repair._pair_insertion_costs
        original_distance = repair._pair_direct_distance
        repair._pair_insertion_costs = lambda instance_arg, routes_arg, pickup, dropoff: costs[(pickup, dropoff)]
        repair._pair_direct_distance = lambda instance_arg, pickup, dropoff: 0.0
        try:
            ordered = repair._hardest_pairs_first(instance, [], pairs)
        finally:
            repair._pair_insertion_costs = original_costs
            repair._pair_direct_distance = original_distance

        self.assertEqual(("blocked-p", "blocked-d"), ordered[0])
        self.assertEqual(("hard-p", "hard-d"), ordered[1])
        self.assertEqual(("easy-p", "easy-d"), ordered[2])

    def test_pair_aware_elimination_hardest_pairs_prioritizes_few_options_first(self) -> None:
        operator = consolidation.PairAwareRouteEliminationOperator()
        instance = {"nodes": [], "distanceMatrix": []}
        pairs = [("easy-p", "easy-d"), ("hard-p", "hard-d"), ("blocked-p", "blocked-d")]
        costs = {
            ("easy-p", "easy-d"): [1.0, 2.0],
            ("hard-p", "hard-d"): [10.0],
            ("blocked-p", "blocked-d"): [],
        }
        original_costs = operator._pair_insertion_costs
        original_distance = operator._pair_direct_distance
        operator._pair_insertion_costs = lambda instance_arg, routes_arg, pickup, dropoff, limit: costs[(pickup, dropoff)]
        operator._pair_direct_distance = lambda instance_arg, pickup, dropoff: 0.0
        try:
            ordered = operator._hardest_pairs_first(instance, [], pairs)
        finally:
            operator._pair_insertion_costs = original_costs
            operator._pair_direct_distance = original_distance

        self.assertEqual(("blocked-p", "blocked-d"), ordered[0])
        self.assertEqual(("hard-p", "hard-d"), ordered[1])
        self.assertEqual(("easy-p", "easy-d"), ordered[2])

    def test_pair_aware_elimination_caps_pair_insertion_checks(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(12)]
        instance = support.normalize_instance("unit", "PDPTW", "cap-unit", 2, 10, nodes, [{"pickupNodeId": "1", "dropoffNodeId": "2"}], {"vehicleCount": 1, "objective": 10.0})
        routes = [["0"] + [str(index) for index in range(3, 11)] + ["0"]]
        operator = consolidation.PairAwareRouteEliminationOperator(route_shortlist=1, max_candidate_checks_per_pair=5)
        calls = {"count": 0}
        original_check = consolidation.check_solution

        def fake_check(instance_arg, solution_arg):
            calls["count"] += 1
            return {"feasible": True, "vehicleCount": 1, "totalDistance": float(calls["count"])}

        consolidation.check_solution = fake_check
        try:
            costs = operator._pair_insertion_costs(instance, routes, "1", "2", limit=2)
        finally:
            consolidation.check_solution = original_check

        self.assertLessEqual(calls["count"], 6)
        self.assertEqual(2, len(costs))

    def test_resource_budget_allocator_degrades_under_hot_lagged_load(self) -> None:
        allocation = resource_core.BudgetAllocator(max_tick_ms=800).allocate(
            resource_core.OptimizerLoadSnapshot(
                order_count=500,
                driver_count=40,
                active_route_count=180,
                queue_lag_ms=6_000,
                hot_partition_ratio=4.5,
                feasible_candidate_ratio=0.4,
            )
        )

        self.assertEqual("L4_SAFE_HOLD", allocation.degrade_level)
        self.assertLessEqual(allocation.repair_ms, 80)
        self.assertGreaterEqual(allocation.reserve_ms, 400)

    def test_resource_budget_allocator_full_mode_when_load_is_healthy(self) -> None:
        allocation = resource_core.BudgetAllocator(max_tick_ms=800).allocate(
            resource_core.OptimizerLoadSnapshot(
                order_count=30,
                driver_count=60,
                active_route_count=12,
                queue_lag_ms=20,
                hot_partition_ratio=1.1,
                feasible_candidate_ratio=0.95,
            )
        )

        self.assertEqual("L0_FULL", allocation.degrade_level)
        self.assertGreaterEqual(allocation.repair_ms, 300)

    def test_hot_key_detector_flags_skewed_partition_load(self) -> None:
        detector = resource_core.HotKeyDetector()

        self.assertTrue(detector.should_split([100, 105, 98, 420], threshold=2.0))
        self.assertFalse(detector.should_split([100, 105, 98, 120], threshold=2.0))

    def test_operator_scoreboard_ranks_accepted_improvements(self) -> None:
        scoreboard = resource_core.OperatorScoreboard()
        scoreboard.record("route-ejection", True, 3, 2, 100.0, 90.0)
        scoreboard.record("distance-swap", True, 2, 2, 90.0, 80.0)
        scoreboard.record("weak-op", False, 2, 2, 80.0, 82.0)

        summary = scoreboard.summary()

        self.assertEqual(3, summary["operatorCount"])
        self.assertEqual("route-ejection", summary["bestOperators"][0])
        self.assertEqual(1.0, summary["operators"]["route-ejection"]["acceptRate"])

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

    def test_route_beauty_quality_score_rewards_clean_routes(self) -> None:
        clean = {"routePolylinePresent": True, "straightnessScore": 0.95, "networkDetourRatio": 1.05, "turnCount": 2, "sharpTurnCount": 0}
        poor = {"routePolylinePresent": True, "straightnessScore": 0.20, "networkDetourRatio": 5.0, "turnCount": 40, "sharpTurnCount": 8}

        self.assertGreater(route_beauty.route_quality_score(clean), route_beauty.route_quality_score(poor))
        self.assertGreater(route_beauty.route_quality_score(clean), 0.90)

    def test_route_beauty_risk_primitives_reward_corridor_fit(self) -> None:
        clean = {"routePolylinePresent": True, "straightnessScore": 0.95, "networkDetourRatio": 1.05, "turnCount": 2, "sharpTurnCount": 0}
        poor = {"routePolylinePresent": True, "straightnessScore": 0.20, "networkDetourRatio": 5.0, "turnCount": 40, "sharpTurnCount": 8}

        clean_risk = route_beauty.route_risk_primitives(clean)
        poor_risk = route_beauty.route_risk_primitives(poor)

        self.assertGreater(clean_risk["routeCorridorFit"], poor_risk["routeCorridorFit"])
        self.assertLess(clean_risk["routeShapePenalty"], poor_risk["routeShapePenalty"])
        self.assertLess(clean_risk["trafficRiskPenalty"], poor_risk["trafficRiskPenalty"])

    def test_route_beauty_selector_exposes_dominance_artifacts(self) -> None:
        graph = {1: [(2, 1.0), (4, 1.2)], 2: [(3, 1.0)], 3: [(6, 1.0)], 4: [(5, 1.2)], 5: [(6, 1.2)], 6: []}
        coordinates = {1: (0.0, 0.0), 2: (1.0, 0.0), 3: (1.0, 1.0), 4: (0.8, 0.1), 5: (1.6, 0.1), 6: (2.0, 0.0)}

        selected = route_beauty.select_beauty_route(graph, coordinates, 1, 6)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIn("routeShapePenalty", selected)
        self.assertIn("routeCorridorFit", selected)
        self.assertIn("trafficRiskPenalty", selected)
        self.assertGreaterEqual(selected["candidateRouteCount"], 1)
        self.assertGreaterEqual(selected["routeSelectionScore"], 0.0)

    def test_elite_route_beauty_uses_quality_score_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "route_beauty_results.json"
            path.write_text(json.dumps({"finalVerdict": "PASS", "avgStraightnessScore": 0.50, "avgNetworkDetourRatio": 2.0, "avgRouteQualityScore": 0.95, "evaluatedPairs": 4}), encoding="utf-8")

            layer = elite.score_road_beauty(root)

        self.assertGreaterEqual(layer["score"], 0.80)
        self.assertEqual(0.95, layer["metrics"]["avgRouteQualityScore"])

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

    def test_mdrplib_hybrid_profile_reports_baseline_delta(self) -> None:
        metrics = mdrplib.evaluate_mdrplib_instance(Path("benchmarks/external/official/mdrplib/mdrp-smoke-low"))

        self.assertEqual("mdrplib-metrics/v9", metrics["schemaVersion"])
        self.assertEqual("product-quality-max-anchor-route-pool-v9", metrics["optimizerMode"])
        self.assertEqual(metrics["orderCount"], metrics["servedOrderCount"])
        self.assertEqual(0, metrics["pickupBeforeReadyTimeViolation"] + metrics["courierShiftViolation"])
        self.assertTrue(metrics["baselineBeaten"])
        self.assertGreaterEqual(metrics["qualityScoreDeltaVsBaseline"], 0.0)
        self.assertIn("baselineMetrics", metrics)
        self.assertGreaterEqual(metrics["portfolioProfileCount"], 19)
        self.assertIn("profileSummaries", metrics)
        repair_profiles = [row for row in metrics["profileSummaries"] if row.get("optimizerFamily") == "route-state-repair"]
        bundle_profiles = [row for row in metrics["profileSummaries"] if row.get("optimizerFamily") == "compatible-multi-restaurant-bundle"]
        alns_profiles = [row for row in metrics["profileSummaries"] if row.get("optimizerFamily") == "alns-lite-food"]
        route_pool_profiles = [row for row in metrics["profileSummaries"] if row.get("optimizerFamily") == "route-pool-set-packing"]
        self.assertTrue(repair_profiles)
        self.assertTrue(bundle_profiles)
        self.assertTrue(alns_profiles)
        self.assertTrue(route_pool_profiles)
        self.assertTrue(metrics["repairMode"].startswith("route-state-relocate-swap-regret-v4"))
        self.assertIn("repairOperatorCounts", metrics)
        self.assertIn("repairImprovementDelta", metrics)
        self.assertTrue(metrics["bundleMode"].startswith("compatible-multi-restaurant-v5"))
        self.assertIn("route-insertion-delta", metrics["bundleCompatibilityFeatures"])
        self.assertIn("bundleEvidenceProfile", metrics)
        self.assertTrue(metrics["alnsMode"].startswith("alns-lite-food-v7"))
        self.assertIn("alnsDestroyOperatorCounts", metrics)
        self.assertIn("alnsRepairOperatorCounts", metrics)
        self.assertIn("alnsBestObjectiveDelta", metrics)
        self.assertIn("operatorLearningRows", metrics)
        self.assertTrue(metrics["routePoolMode"].startswith("route-pool-set-packing-v8"))
        self.assertEqual("top-k-corridor-risk-v2", metrics["anchorMode"])
        self.assertIn("anchorV2Score", metrics)
        self.assertIn("anchorReadySlack", metrics)
        self.assertIn("anchorCorridorFit", metrics)
        self.assertIn("anchorDetourRisk", metrics)
        self.assertIn("anchorTrafficRisk", metrics)
        self.assertGreaterEqual(metrics["anchorFeatureCandidateCount"], 1)
        self.assertFalse(metrics["fallbackAllowed"])
        self.assertIn("candidatePoolSize", metrics)
        self.assertIn("paretoFrontSize", metrics)
        self.assertIn("dominanceRejectedCandidates", metrics)
        self.assertIn("setPackingFallbackUsed", metrics)
        self.assertIn("routeFragmentCandidateCount", metrics)
        self.assertIn("targetLoad", metrics)
        self.assertIn("overloadedCourierCount", metrics)
        self.assertIn("loadBalancingMoves", metrics)
        self.assertIn("beautyAwareCandidateCount", metrics)
        self.assertIn("selectedBeautyScoreAvg", metrics)
        self.assertIn("routeShapePenalty", metrics)
        self.assertIn("routeCorridorFit", metrics)
        self.assertIn("postSelectionRepairApplied", metrics)
        self.assertIn("postPackingIntraRouteMoves", metrics)
        self.assertIn("setPackingRawObjectiveDelta", metrics)

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

    def test_ml_verdict_passes_when_value_and_workers_are_ready(self) -> None:
        adapter = {"workerReadinessAudited": True, "routeFinderWorkerReady": True, "greedRlWorkerReady": True, "forecastWorkerReady": True}
        value = {"mlValueProven": True}

        verdict = ml_quality.ml_verdict(adapter, value)

        self.assertEqual("PASS", verdict["finalVerdict"])
        self.assertEqual([], verdict["verdictReasons"])

    def test_ml_verdict_limits_when_audited_worker_is_not_ready(self) -> None:
        adapter = {"workerReadinessAudited": True, "routeFinderWorkerReady": True, "greedRlWorkerReady": True, "forecastWorkerReady": False}
        value = {"mlValueProven": True}

        verdict = ml_quality.ml_verdict(adapter, value)

        self.assertEqual("PASS_WITH_LIMITS", verdict["finalVerdict"])
        self.assertIn("ml-worker-not-ready", verdict["verdictReasons"])

    def test_ml_verdict_limits_when_value_is_not_proven(self) -> None:
        adapter = {"workerReadinessAudited": True, "routeFinderWorkerReady": True, "greedRlWorkerReady": True, "forecastWorkerReady": True}
        value = {"mlValueProven": False}

        verdict = ml_quality.ml_verdict(adapter, value)

        self.assertEqual("PASS_WITH_LIMITS", verdict["finalVerdict"])
        self.assertIn("ml-value-not-proven", verdict["verdictReasons"])

    def test_baseline_competitiveness_reports_root_cause(self) -> None:
        rows = [{"stage": "A-academic-correctness", "suite": "solomon", "instance": "R101", "verdict": "PASS_WITH_LIMITS", "vehicleCount": 20, "bestKnownVehicleCount": 19}]

        with tempfile.TemporaryDirectory() as temp_dir:
            layer = elite.score_baseline_competitiveness(rows, Path(temp_dir) / "max", Path(temp_dir) / "pyvrp")

        self.assertEqual("vehicle-count", layer["metrics"]["strongBaselineGapRootCause"])


if __name__ == "__main__":
    unittest.main()

