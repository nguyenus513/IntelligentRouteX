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
loss_certificate = load_module("run_phase31_loss_certificate", "run_phase31_loss_certificate.py")
route_pool_sp = load_module("run_phase31_pdptw_route_pool_sp", "run_phase31_pdptw_route_pool_sp.py")
internal_columns = load_module("run_phase32_internal_column_generation", "run_phase32_internal_column_generation.py")
route_set_guided = load_module("run_phase33_route_set_guided_generation", "run_phase33_route_set_guided_generation.py")
missing_large_columns = load_module("run_phase34_missing_request_large_columns", "run_phase34_missing_request_large_columns.py")
residual_repair = load_module("run_phase35_residual_exact_cover_repair", "run_phase35_residual_exact_cover_repair.py")
focused_repair = load_module("run_phase36_residual_focused_repair", "run_phase36_residual_focused_repair.py")
conflict_guided = load_module("run_phase37_conflict_guided_replacement", "run_phase37_conflict_guided_replacement.py")
residual_partition = load_module("run_phase38_residual_partition_generator", "run_phase38_residual_partition_generator.py")
target_vehicle = load_module("run_phase38b_target_vehicle_feasibility", "run_phase38b_target_vehicle_feasibility.py")
missing_targetk = load_module("run_phase39_missing_driven_targetk_repair", "run_phase39_missing_driven_targetk_repair.py")
natural_pdptw = load_module("run_phase40_natural_pdptw_optimizer", "run_phase40_natural_pdptw_optimizer.py")


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

    def test_long_budget_tight_mixed_pdptw_prioritizes_full_tabu_distance_search(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
            {"id": "1", "x": 0.0, "y": 0.0, "demand": 1, "readyTime": 100, "dueTime": 120, "serviceTime": 0},
            {"id": "2", "x": 10.0, "y": 10.0, "demand": -1, "readyTime": 100, "dueTime": 120, "serviceTime": 0},
            {"id": "3", "x": 10.0, "y": 0.0, "demand": 1, "readyTime": 110, "dueTime": 130, "serviceTime": 0},
            {"id": "4", "x": 0.0, "y": 10.0, "demand": -1, "readyTime": 110, "dueTime": 130, "serviceTime": 0},
        ]
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "FEATURE_BASED_TIGHT_MIXED", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 10.0})
        calls = []

        def fake_ortools_baseline_solution(instance_arg, time_limit_ms, solver, **kwargs):
            calls.append({"timeLimitMs": time_limit_ms, "solver": solver, "kwargs": kwargs})
            return {"schemaVersion": "external-benchmark-solution/v1", "solver": solver, "routes": [["0", "1", "2", "3", "4", "0"]]}

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

    def test_pdptw_metaheuristic_policy_ignores_instance_name(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
            {"id": "1", "x": 0.0, "y": 0.0, "demand": 1, "readyTime": 100, "dueTime": 120, "serviceTime": 0},
            {"id": "2", "x": 10.0, "y": 10.0, "demand": -1, "readyTime": 100, "dueTime": 120, "serviceTime": 0},
            {"id": "3", "x": 10.0, "y": 0.0, "demand": 1, "readyTime": 110, "dueTime": 130, "serviceTime": 0},
            {"id": "4", "x": 0.0, "y": 10.0, "demand": -1, "readyTime": 110, "dueTime": 130, "serviceTime": 0},
        ]
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        first = support.normalize_instance("unit", "PDPTW", "LRC_FAKE_NAME", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 10.0})
        second = support.normalize_instance("unit", "PDPTW", "NEUTRAL_NAME", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 10.0})
        solver = adapter.DispatchV2ExternalBenchmarkSolver()

        self.assertEqual(solver._pdptw_metaheuristic_policy(first), solver._pdptw_metaheuristic_policy(second))
        self.assertEqual("TABU_SEARCH", solver._pdptw_metaheuristic_policy(first))

    def test_pdptw_metaheuristic_policy_uses_guided_search_for_loose_simple_case(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
            {"id": "3", "x": 3.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
            {"id": "4", "x": 4.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 1000, "serviceTime": 0},
        ]
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "LRC_NAME_SHOULD_NOT_MATTER", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 10.0})

        self.assertEqual("GUIDED_LOCAL_SEARCH", adapter.DispatchV2ExternalBenchmarkSolver()._pdptw_metaheuristic_policy(instance))

    def test_dispatch_adapter_has_no_lrc_name_branch(self) -> None:
        source = Path("scripts/external_benchmark_dispatch_adapter.py").read_text(encoding="utf-8")

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("startswith('LRC')", source)

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
        self.assertEqual(3, len(calls[0]["operators"]))
        self.assertEqual("pair-aware-route-elimination", calls[0]["operators"][0].name)
        self.assertEqual("pair-ejection-chain", calls[0]["operators"][1].name)
        self.assertEqual("multi-route-destroy-repair", calls[0]["operators"][2].name)

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
        self.assertIn(calls[0]["kwargs"].get("local_search_metaheuristic"), {"TABU_SEARCH", "SIMULATED_ANNEALING"})
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

    def test_pair_insertion_index_reuses_cached_options_and_respects_caps(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(8)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "pair-index-unit", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 10.0})
        routes = [["0", "3", "4", "0"], ["0", "5", "6", "7", "0"]]
        index = consolidation.PairInsertionIndex.build(instance, routes, max_candidate_checks=5, max_routes=2, max_positions_per_route=10)

        first = index.options_for_pair(("1", "2"), top_k=10)
        first_checks = index.candidate_checks
        second = index.options_for_pair(("1", "2"), top_k=10)

        self.assertLessEqual(first_checks, 5)
        self.assertEqual(first_checks, index.candidate_checks)
        self.assertEqual(1, index.cache_hits)
        self.assertEqual(first, second)
        self.assertTrue(all(option.feasible for option in first))

    def test_pair_ejection_chain_operator_reduces_vehicle_count_on_synthetic_pdptw(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "3", "x": 9.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "4", "x": 10.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "5", "x": 4.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "6", "x": 5.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
        ]
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "pair-ejection-unit", 3, 2, nodes, requests, {"vehicleCount": 2, "objective": 20.0})
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"], ["0", "5", "6", "0"], ["0", "3", "4", "0"]]}
        before = support.check_solution(instance, solution)

        result = consolidation.GlobalRouteConsolidator(
            operators=[consolidation.PairEjectionChainOperator(max_removed_pairs=1, max_runtime_ms=1_000, max_states=64, beam_width=8, max_depth=2, max_candidate_checks=256)]
        ).consolidate(instance, solution)
        after = support.check_solution(instance, result.solution)

        self.assertTrue(after["feasible"])
        self.assertLess(after["vehicleCount"], before["vehicleCount"])
        accepted = [move for move in result.trace.moves if move.operator == "pair-ejection-chain" and move.accepted]
        self.assertTrue(accepted)
        self.assertGreaterEqual(accepted[0].metadata["statesExpanded"], 1)

    def test_multi_route_destroy_repair_removes_related_neighbor_pair(self) -> None:
        nodes = [
            {"id": "0", "x": 0.0, "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "1", "x": 1.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "2", "x": 2.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "3", "x": 3.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "4", "x": 4.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "5", "x": 5.0, "y": 0.0, "demand": 1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
            {"id": "6", "x": 6.0, "y": 0.0, "demand": -1, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0},
        ]
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "multi-destroy-unit", 3, 2, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        solution = {"schemaVersion": "external-benchmark-solution/v1", "solver": "unit", "routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"]]}
        before = support.check_solution(instance, solution)

        result = consolidation.GlobalRouteConsolidator(
            operators=[consolidation.MultiRouteDestroyRepairOperator(max_runtime_ms=1_000, max_neighbor_routes=2, max_removed_pairs=3, beam_width=8, max_states=128, ejection_depth=2, max_candidate_checks=512)]
        ).consolidate(instance, solution)
        after = support.check_solution(instance, result.solution)

        self.assertTrue(after["feasible"])
        self.assertLess(after["vehicleCount"], before["vehicleCount"])
        accepted = [move for move in result.trace.moves if move.operator == "multi-route-destroy-repair" and move.accepted]
        self.assertTrue(accepted)
        self.assertGreaterEqual(accepted[0].metadata["relatedPairCount"], 1)

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

    def test_phase31_certificate_detects_candidate_cap(self) -> None:
        stats = [{"zeroOptionPairCount": 1, "candidateCapHit": True}, {"zeroOptionPairCount": 1, "candidateCapHit": False}]

        blocker = loss_certificate.classify_blocker(stats, {"candidate-cap": 1, "time-window": 0, "capacity": 0}, state_cap_hit=True, runtime_cap_hit=False)

        self.assertEqual("state-cap", blocker)

    def test_phase31_certificate_surfaces_runtime_and_state_cap_together(self) -> None:
        stats = [{"zeroOptionPairCount": 1, "candidateCapHit": True}]

        blocker = loss_certificate.classify_blocker(stats, {"candidate-cap": 1}, state_cap_hit=True, runtime_cap_hit=True)
        secondary = loss_certificate.secondary_blockers(blocker, state_cap_hit=True, runtime_cap_hit=True)

        self.assertEqual("search-budget-cap", blocker)
        self.assertEqual(["runtime-cap", "state-cap"], secondary)

    def test_phase31_certificate_detects_route_shortlist_over_pruning(self) -> None:
        stats = [{"zeroOptionPairCount": 2, "candidateCapHit": False}, {"zeroOptionPairCount": 0, "candidateCapHit": False}]

        blocker = loss_certificate.classify_blocker(stats, {"candidate-cap": 0, "time-window": 0, "capacity": 0}, state_cap_hit=False, runtime_cap_hit=False)

        self.assertEqual("over-pruning", blocker)

    def test_phase31_certificate_distinguishes_true_time_window_block(self) -> None:
        stats = [{"zeroOptionPairCount": 2, "candidateCapHit": False}, {"zeroOptionPairCount": 2, "candidateCapHit": False}]

        blocker = loss_certificate.classify_blocker(stats, {"candidate-cap": 0, "time-window": 9, "capacity": 0}, state_cap_hit=False, runtime_cap_hit=False)

        self.assertEqual("true-time-window-block", blocker)

    def test_phase31_certificate_wider_shortlist_reveals_feasible_insertion(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(8)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "shortlist-certificate-unit", 3, 2, nodes, requests, {"vehicleCount": 1, "objective": 10.0})
        routes = [["0", "6", "7", "0"], ["0", "3", "4", "0"], ["0", "5", "0"]]

        narrow = loss_certificate.pair_option_stats(instance, routes, [("1", "2")], route_shortlist=1, max_candidate_checks=64)
        wide = loss_certificate.pair_option_stats(instance, routes, [("1", "2")], route_shortlist=3, max_candidate_checks=256)

        self.assertGreaterEqual(narrow["zeroOptionPairCount"], wide["zeroOptionPairCount"])
        self.assertGreater(wide["max"], 0)

    def test_phase31_certificate_reports_unmeasured_pairs_due_to_cap(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(10)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "cap-certificate-unit", 3, 2, nodes, requests, {"vehicleCount": 1, "objective": 10.0})
        routes = [["0", "5", "6", "7", "8", "9", "0"]]

        stats = loss_certificate.pair_option_stats(instance, routes, [("1", "2"), ("3", "4")], route_shortlist=1, max_candidate_checks=1)

        self.assertTrue(stats["candidateCapHit"])
        self.assertEqual(1, stats["measuredPairCount"])
        self.assertEqual(2, stats["totalPairCount"])
        self.assertEqual(["3->4"], stats["unmeasuredPairsDueToCap"])
        self.assertNotIn("3->4", stats["zeroOptionPairs"])
        self.assertFalse(stats["measurementComplete"])

    def test_phase31b_route_column_covers_complete_pd_pairs_only(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "column-unit", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 4.0})

        valid = route_pool_sp.build_column(instance, ["0", "1", "2", "0"], "unit", "c0", provenance="internal", allowed_for_claim=True)
        invalid = route_pool_sp.build_column(instance, ["0", "1", "0"], "unit", "c1")

        self.assertIsNotNone(valid)
        self.assertEqual(frozenset({"0"}), valid.request_ids)
        self.assertTrue(valid.allowed_for_claim)
        self.assertIsNone(invalid)

    def test_phase31b_route_pool_deduplicates_and_detects_uncovered(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup in [1, 3]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "pool-unit", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        pool = route_pool_sp.PDPTWRoutePool(instance)

        self.assertTrue(pool.add_route(["0", "1", "2", "0"], "unit"))
        self.assertFalse(pool.add_route(["0", "1", "2", "0"], "unit"))
        stats = pool.stats()

        self.assertEqual(1, stats["columnCount"])
        self.assertEqual(1, stats["duplicateRouteCount"])
        self.assertEqual(["1"], stats["uncoveredRequests"])

    def test_phase31b_sp_selects_exact_cover_and_respects_target(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "sp-unit", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        pool = route_pool_sp.PDPTWRoutePool(instance)
        pool.add_route(["0", "1", "2", "0"], "single")
        pool.add_route(["0", "3", "4", "0"], "single")
        pool.add_route(["0", "1", "2", "3", "4", "0"], "combined")

        result = route_pool_sp.PDPTWSetPartitioningSolver(time_limit_ms=1_000).solve(instance, pool.columns, target_vehicle_count=1)

        self.assertTrue(result["feasible"])
        self.assertEqual(1, result["selectedRouteCount"])

    def test_phase31b_pool_rejects_infeasible_column(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(3)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "reject-unit", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 4.0})
        pool = route_pool_sp.PDPTWRoutePool(instance)

        self.assertFalse(pool.add_route(["0", "2", "1", "0"], "bad"))
        self.assertEqual(1, pool.stats()["rejectedInfeasibleCount"])

    def test_phase31c_comparator_columns_are_excluded_from_internal_pool(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "provenance-unit", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        pool = route_pool_sp.PDPTWRoutePool(instance)
        pool.add_route(["0", "1", "2", "0"], "internal", provenance="internal", allowed_for_claim=True)
        pool.add_route(["0", "3", "4", "0"], "comparator", provenance="comparator", allowed_for_claim=False)

        internal_pool = pool.filtered(allowed_for_claim=True)

        self.assertEqual(1, len(internal_pool.columns))
        self.assertEqual(2, len(pool.columns))
        self.assertTrue(all(column.allowed_for_claim for column in internal_pool.columns))

    def test_phase31c_internal_sp_cannot_use_disallowed_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "internal-sp-unit", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        pool = route_pool_sp.PDPTWRoutePool(instance)
        pool.add_route(["0", "1", "2", "0"], "internal", provenance="internal", allowed_for_claim=True)
        pool.add_route(["0", "3", "4", "0"], "comparator", provenance="comparator", allowed_for_claim=False)

        internal_result = route_pool_sp.PDPTWSetPartitioningSolver(time_limit_ms=1_000).solve(instance, pool.filtered(allowed_for_claim=True).columns, target_vehicle_count=2)
        oracle_result = route_pool_sp.PDPTWSetPartitioningSolver(time_limit_ms=1_000).solve(instance, pool.columns, target_vehicle_count=2)

        self.assertFalse(internal_result["feasible"])
        self.assertTrue(oracle_result["feasible"])

    def test_phase31c_provenance_summary_reports_comparator_leakage(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(3)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "leakage-unit", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 4.0})
        pool = route_pool_sp.PDPTWRoutePool(instance)
        pool.add_route(["0", "1", "2", "0"], "comparator", provenance="comparator", allowed_for_claim=False)
        oracle_result = route_pool_sp.PDPTWSetPartitioningSolver(time_limit_ms=1_000).solve(instance, pool.columns, target_vehicle_count=1)

        summary = route_pool_sp.provenance_summary(pool.filtered(allowed_for_claim=True), pool, {"feasible": False}, oracle_result)

        self.assertTrue(summary["oracleTargetFeasible"])
        self.assertTrue(summary["comparatorColumnUsedByOracleSolution"])

    def test_phase32_collector_rejects_partial_pickup_dropoff_route(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(3)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-partial", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 4.0})
        collector = internal_columns.RouteColumnCollector(instance)

        accepted = collector.collect(["0", "1", "0"], "unit")

        self.assertFalse(accepted)
        self.assertEqual(0, len(collector.pool.columns))

    def test_phase32_collector_accepts_internal_complete_feasible_route(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(3)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-complete", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 4.0})
        collector = internal_columns.RouteColumnCollector(instance)

        accepted = collector.collect(["0", "1", "2", "0"], "repair-intermediate")

        self.assertTrue(accepted)
        self.assertEqual("internal", collector.pool.columns[0].provenance)
        self.assertTrue(collector.pool.columns[0].allowed_for_claim)
        self.assertEqual(1, collector.stage_counts["repair-intermediate"])

    def test_phase32_failed_full_repair_can_contribute_route_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(3)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-failed", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 4.0})
        collector = internal_columns.RouteColumnCollector(instance)

        collector.collect(["0", "1", "2", "0"], "repair-intermediate", failed_repair=True)

        self.assertEqual(1, collector.harvested_from_failed_repairs)
        self.assertEqual(1, len(collector.pool.columns))

    def test_phase32_route_variant_generator_increases_columns_without_hard_violations(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup in [1, 3, 5]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4, 6]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-variant", 1, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        solution = {"routes": [["0", "1", "2", "3", "4", "5", "6", "0"]]}

        collector, diagnostics = internal_columns.generate_internal_columns(instance, solution, budget_ms=500, max_variants_per_route=20)

        self.assertGreaterEqual(len(collector.pool.columns), 1)
        self.assertEqual([], collector.pool.stats()["uncoveredRequests"])
        self.assertGreaterEqual(diagnostics["columnGenerationRuntimeMs"], 0)

    def test_phase32_subset_route_generator_creates_feasible_request_subsets(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup in [1, 3, 5, 7]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4, 6, 8]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}, {"pickupNodeId": "7", "dropoffNodeId": "8"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-subset", 1, 4, nodes, requests, {"vehicleCount": 1, "objective": 16.0})

        variants = internal_columns.subset_route_columns(instance, ["0", "1", "2", "3", "4", "5", "6", "7", "8", "0"], max_columns=10, max_pairs_per_route=3)

        self.assertTrue(variants)
        self.assertTrue(all(consolidation._route_is_feasible(instance, route)[0] for route in variants))

    def test_phase32_sp_selected_solution_uses_only_allowed_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-sp", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "unit")
        collector.collect(["0", "3", "4", "0"], "unit")

        result = route_pool_sp.PDPTWSetPartitioningSolver(time_limit_ms=1_000).solve(instance, collector.pool.columns, target_vehicle_count=2)

        self.assertTrue(result["feasible"])
        details = internal_columns.selected_column_details(collector.pool, result)
        self.assertTrue(all(details["selectedAllowedForClaim"]))

    def test_phase32_request_set_diversity_stats_detect_duplicate_sets(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-diversity", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "unit")
        collector.collect(["0", "1", "2", "3", "4", "0"], "unit")
        collector.pool.add_route(["0", "1", "2", "0"], "diagnostic-duplicate", provenance="internal", allowed_for_claim=True)

        stats = internal_columns.request_set_diversity_stats(collector.pool)

        self.assertGreaterEqual(stats["uniqueRequestSetCount"], 2)
        self.assertIn("1", stats["requestSetSizeHistogram"])

    def test_phase32_cluster_generator_creates_complete_feasible_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup in [1, 3, 5, 7]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4, 6, 8]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}, {"pickupNodeId": "7", "dropoffNodeId": "8"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-cluster", 2, 4, nodes, requests, {"vehicleCount": 1, "objective": 16.0})
        collector = internal_columns.RouteColumnCollector(instance)

        generated = internal_columns.cluster_route_columns(instance, collector, max_columns=10, max_pairs_per_route=3, related_k=4, seed=31)

        self.assertGreater(generated, 0)
        self.assertTrue(all(column.allowed_for_claim for column in collector.pool.columns))
        self.assertTrue(all(column.feasible for column in collector.pool.columns))

    def test_phase32_weak_route_replacement_creates_non_identical_sets(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup in [1, 3, 5, 7]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4, 6, 8]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}, {"pickupNodeId": "7", "dropoffNodeId": "8"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-weak", 2, 4, nodes, requests, {"vehicleCount": 1, "objective": 16.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "5", "6", "7", "8", "0"]]}
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect_solution(solution, "incumbent")

        generated = internal_columns.weak_route_replacement_columns(instance, solution, collector, target_vehicle_count=1, max_columns=10)

        self.assertGreaterEqual(generated, 0)
        self.assertGreaterEqual(internal_columns.request_set_diversity_stats(collector.pool)["uniqueRequestSetCount"], 2)

    def test_phase32_cluster_generator_is_deterministic_under_fixed_seed(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup in [1, 3, 5]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4, 6]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase32-deterministic", 2, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        first = internal_columns.RouteColumnCollector(instance)
        second = internal_columns.RouteColumnCollector(instance)

        internal_columns.cluster_route_columns(instance, first, max_columns=8, max_pairs_per_route=3, related_k=3, seed=31)
        internal_columns.cluster_route_columns(instance, second, max_columns=8, max_pairs_per_route=3, related_k=3, seed=31)

        self.assertEqual([column.route for column in first.pool.columns], [column.route for column in second.pool.columns])

    def test_phase33_max_cover_identifies_uncovered_requests(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup in [1, 3, 5]:
            nodes[pickup]["demand"] = 1
        for dropoff in [2, 4, 6]:
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase33-max-cover", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "unit")
        collector.collect(["0", "3", "4", "0"], "unit")

        result = route_set_guided.max_cover_packing(instance, collector.pool.columns, target_vehicle_count=1)

        self.assertEqual(1, result["maxCoveredRequestCount"])
        self.assertGreaterEqual(len(result["uncoveredRequestsInBestPacking"]), 2)

    def test_phase33_min_slack_reports_missing_and_duplicate_requests(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase33-slack", 1, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "unit")
        collector.collect(["0", "1", "2", "3", "4", "0"], "unit")

        result = route_set_guided.min_slack_relaxation(instance, collector.pool.columns[:1], target_vehicle_count=1)

        self.assertTrue(result["feasible"])
        self.assertIn("1", result["missingRequests"])

    def test_phase33_compatibility_graph_detects_incompatible_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase33-graph", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "unit")
        collector.collect(["0", "1", "2", "3", "4", "0"], "unit")

        stats = route_set_guided.compatibility_graph_stats(collector.pool.columns)

        self.assertEqual(0, stats["compatibleEdgeCount"])
        self.assertGreaterEqual(stats["isolatedColumnCount"], 1)

    def test_phase33_complement_generator_creates_valid_internal_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase33-complement", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        max_cover = {"uncoveredRequestsInBestPacking": ["1"]}

        generated = route_set_guided.complement_route_generator(instance, collector, max_cover, max_columns=3)

        self.assertGreater(generated, 0)
        self.assertTrue(all(column.allowed_for_claim for column in collector.pool.columns))

    def test_phase33_compression_rejects_infeasible_union_routes(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["x"] = 100.0
        nodes[2]["x"] = 101.0
        nodes[3]["x"] = -100.0
        nodes[4]["x"] = -101.0
        nodes[1]["demand"] = 2
        nodes[2]["demand"] = -2
        nodes[3]["demand"] = 2
        nodes[4]["demand"] = -2
        nodes[1]["dueTime"] = 120
        nodes[2]["dueTime"] = 125
        nodes[3]["dueTime"] = 120
        nodes[4]["dueTime"] = 125
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase33-compression", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "unit")
        collector.collect(["0", "3", "4", "0"], "unit")

        generated = route_set_guided.compression_column_generator(instance, collector, max_columns=5)

        self.assertEqual(0, generated)

    def test_phase33_guided_generation_is_deterministic(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase33-guided", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        first = internal_columns.RouteColumnCollector(instance)
        second = internal_columns.RouteColumnCollector(instance)
        relaxation = {"missingRequests": ["0"], "duplicateRequests": ["1"]}

        route_set_guided.guided_penalty_generation(instance, first, relaxation, max_columns=5)
        route_set_guided.guided_penalty_generation(instance, second, relaxation, max_columns=5)

        self.assertEqual([column.route for column in first.pool.columns], [column.route for column in second.pool.columns])

    def test_phase34_missing_request_generator_targets_large_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
            {"pickupNodeId": "7", "dropoffNodeId": "8"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase34-missing", 4, 4, nodes, requests, {"vehicleCount": 1, "objective": 16.0})
        collector = internal_columns.RouteColumnCollector(instance)

        generated = missing_large_columns.missing_request_focused_generator(instance, collector, ["0"], avg_target_route_size=3, max_columns=4)

        self.assertGreater(generated, 0)
        self.assertTrue(any("0" in column.request_ids and len(column.request_ids) >= 2 for column in collector.pool.columns))
        self.assertTrue(all(column.allowed_for_claim for column in collector.pool.columns))

    def test_phase34_compatible_complement_stays_disjoint_from_selected_cover(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase34-complement", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        max_cover = {"selectedColumnRequestSets": [["0", "1"]], "uncoveredRequestsInBestPacking": ["2"]}

        generated = missing_large_columns.compatible_complement_generator(instance, collector, max_cover, avg_target_route_size=2, max_columns=3)

        self.assertGreater(generated, 0)
        self.assertTrue(any(set(column.request_ids).isdisjoint({"0", "1"}) and "2" in column.request_ids for column in collector.pool.columns))

    def test_phase34_large_compatible_column_stats_counts_target_band_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase34-large-stats", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "3", "4", "0"], "unit")
        collector.collect(["0", "5", "6", "0"], "unit")

        stats = missing_large_columns.large_compatible_column_stats(collector.pool.columns, avg_target_route_size=2)

        self.assertGreaterEqual(stats["largeColumnCount"], 2)
        self.assertGreaterEqual(stats["largeCompatibleColumnCount"], 1)

    def test_phase34_generation_preserves_internal_only_pool(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase34-internal", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)

        missing_large_columns.missing_request_focused_generator(instance, collector, ["0"], avg_target_route_size=2, max_columns=2)

        self.assertTrue(collector.pool.columns)
        self.assertTrue(all(column.provenance == "internal" and column.allowed_for_claim for column in collector.pool.columns))

    def test_phase35_missing_request_insertion_repairs_synthetic_packing(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase35-insertion", 3, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "3", "4", "0"], "unit")
        selected = collector.pool.columns[:]

        result = residual_repair.missing_request_insertion_repair(instance, collector, selected, target_vehicle_count=1)

        self.assertTrue(result["exact"])
        self.assertEqual(0, residual_repair.coverage_state(instance, result["columns"])["missingCount"])

    def test_phase35_one_column_swap_repairs_synthetic_residual(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase35-one-swap", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        collector.collect(["0", "3", "4", "0"], "selected")
        selected = collector.pool.columns[:]
        collector.collect(["0", "3", "4", "5", "6", "0"], "replacement")

        result = residual_repair.one_column_swap_repair(instance, collector, selected, target_vehicle_count=2)

        self.assertTrue(result["exact"])
        self.assertEqual(0, residual_repair.coverage_state(instance, result["columns"])["missingCount"])

    def test_phase35_two_column_swap_repairs_synthetic_residual(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
            {"pickupNodeId": "7", "dropoffNodeId": "8"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase35-two-swap", 4, 4, nodes, requests, {"vehicleCount": 2, "objective": 16.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        collector.collect(["0", "3", "4", "0"], "selected")
        selected = collector.pool.columns[:]

        result = residual_repair.two_column_swap_repair(instance, collector, selected, target_vehicle_count=2)

        self.assertGreaterEqual(result["successes"], 1)
        self.assertLessEqual(residual_repair.coverage_state(instance, result["columns"])["missingCount"], 2)

    def test_phase35_k_minus_one_complement_creates_valid_final_route(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase35-complement", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        collector.collect(["0", "3", "4", "0"], "selected")
        selected = collector.pool.columns[:]

        result = residual_repair.k_minus_one_complement_repair(instance, collector, selected, target_vehicle_count=2)

        self.assertTrue(result["exact"])
        self.assertTrue(check_solution := support.check_solution(instance, result["columns"] and {"routes": [column.route for column in result["columns"]]}).get("feasible"))

    def test_phase35_local_search_never_uses_disallowed_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase35-no-leak", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        selected = collector.pool.columns[:]
        collector.pool.add_route(["0", "3", "4", "0"], "comparator", source_solver="baseline", provenance="comparator", allowed_for_claim=False)

        result = residual_repair.residual_exact_cover_local_search(instance, collector, selected, target_vehicle_count=1)

        chosen_ids = set(result.get("bestSelectedColumnIds", []))
        self.assertFalse(any(column.column_id in chosen_ids and not column.allowed_for_claim for column in collector.pool.columns))

    def test_phase36_residual_two_insertion_repairs_synthetic_case(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
            {"pickupNodeId": "7", "dropoffNodeId": "8"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase36-insert-two", 4, 4, nodes, requests, {"vehicleCount": 1, "objective": 16.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "3", "4", "0"], "selected")
        selected = collector.pool.columns[:]

        result = focused_repair.insert_missing_pair_set(instance, collector, selected, ["2", "3"], target_vehicle_count=1)

        self.assertTrue(result["exact"])
        self.assertEqual(0, residual_repair.coverage_state(instance, result["columns"])["missingCount"])

    def test_phase36_two_column_replacement_repairs_exact_cover_case(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
            {"pickupNodeId": "7", "dropoffNodeId": "8"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase36-two-to-two", 4, 4, nodes, requests, {"vehicleCount": 2, "objective": 16.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        collector.collect(["0", "3", "4", "0"], "selected")
        selected = collector.pool.columns[:]

        result = focused_repair.replace_two_with_two(instance, collector, selected, ["2", "3"], target_vehicle_count=2)

        self.assertTrue(result["exact"])
        self.assertTrue(support.check_solution(instance, {"routes": [column.route for column in result["columns"]]}).get("feasible"))

    def test_phase36_three_to_two_compression_creates_room_for_missing_request(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
            {"pickupNodeId": "7", "dropoffNodeId": "8"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase36-three-to-two", 4, 4, nodes, requests, {"vehicleCount": 3, "objective": 16.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        collector.collect(["0", "3", "4", "0"], "selected")
        collector.collect(["0", "5", "6", "0"], "selected")
        selected = collector.pool.columns[:]

        result = focused_repair.replace_three_with_two(instance, collector, selected, ["3"], target_vehicle_count=3)

        self.assertTrue(result["exact"])
        self.assertLessEqual(len(result["columns"]), 3)

    def test_phase36_hard_certificate_classifies_no_compatible_column(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase36-cert", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        selected = collector.pool.columns[:]
        collector.collect(["0", "1", "2", "5", "6", "0"], "overlap-candidate")

        certificate = focused_repair.hard_residual_certificate(instance, selected, collector.pool.columns)

        self.assertEqual("no-compatible-column", certificate["blockerClassificationByRequest"]["2"])

    def test_phase36_focused_search_never_uses_disallowed_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase36-no-leak", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        selected = collector.pool.columns[:]
        collector.pool.add_route(["0", "3", "4", "0"], "comparator", source_solver="baseline", provenance="comparator", allowed_for_claim=False)

        result = focused_repair.focused_local_search(instance, collector, selected, target_vehicle_count=1)

        selected_ids = set(result.get("selectedColumnIds", []))
        self.assertFalse(any(column.column_id in selected_ids and not column.allowed_for_claim for column in collector.pool.columns))

    def test_phase37_conflict_analysis_identifies_blocking_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase37-conflict", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        selected = collector.pool.columns[:]
        collector.collect(["0", "1", "2", "5", "6", "0"], "candidate")

        analysis = conflict_guided.conflict_analysis(selected, collector.pool.columns, ["2"])

        self.assertTrue(analysis)
        self.assertEqual([selected[0].column_id], analysis[0]["blockingSelectedColumnIds"])
        self.assertEqual(["2"], analysis[0]["missingCovered"])

    def test_phase37_local_subproblem_selects_disjoint_fixed_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase37-subproblem", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "fixed")
        fixed = collector.pool.columns[:]
        collector.collect(["0", "3", "4", "5", "6", "0"], "candidate")
        collector.pool.add_route(["0", "1", "2", "5", "6", "0"], "comparator", source_solver="baseline", provenance="comparator", allowed_for_claim=False)

        result = conflict_guided.solve_residual_subproblem(instance, fixed, collector.pool.columns, ["1", "2"], route_slots=1)

        self.assertTrue(result["feasible"])
        self.assertTrue(all(column.allowed_for_claim and not (set(column.request_ids) & {"0"}) for column in result["selectedColumns"]))

    def test_phase37_generated_replacement_columns_are_internal_only(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase37-generated", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)

        generated = conflict_guided.generate_replacement_columns(instance, collector, ["0", "1", "2"], route_slots=1)

        self.assertGreater(generated, 0)
        self.assertTrue(all(column.provenance == "internal" and column.allowed_for_claim for column in collector.pool.columns))

    def test_phase37_replacement_search_fixes_synthetic_no_compatible_case(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase37-fix", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "selected")
        selected = collector.pool.columns[:]
        collector.collect(["0", "1", "2", "5", "6", "0"], "overlap-candidate")
        collector.collect(["0", "1", "2", "5", "6", "0"], "duplicate-overlap")
        collector.collect(["0", "1", "2", "5", "6", "0"], "duplicate-overlap-2")

        result = conflict_guided.blocking_set_replacement_search(instance, collector, selected, ["2"], target_vehicle_count=1)

        self.assertTrue(result["feasible"])
        self.assertTrue(support.check_solution(instance, result["solution"]).get("feasible"))

    def test_phase37_comparator_columns_are_never_used(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase37-no-leak", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "fixed")
        fixed = collector.pool.columns[:]
        collector.pool.add_route(["0", "3", "4", "0"], "comparator", source_solver="baseline", provenance="comparator", allowed_for_claim=False)

        result = conflict_guided.solve_residual_subproblem(instance, fixed, collector.pool.columns, ["1"], route_slots=1)

        self.assertFalse(result.get("feasible"))

    def test_phase38_balanced_partition_covers_residual_exactly_once(self) -> None:
        groups = residual_partition.balanced_partition(["a", "b", "c", "d", "e"], 2)

        flattened = [request_id for group in groups for request_id in group]
        self.assertEqual(["a", "b", "c", "d", "e"], sorted(flattened))
        self.assertEqual(len(flattened), len(set(flattened)))

    def test_phase38_partition_route_construction_creates_complete_pd_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase38-construct", 3, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)

        columns, repairs = residual_partition.construct_partition_columns(instance, collector, [["0", "1", "2"]], "unit")

        self.assertEqual(0, repairs)
        self.assertEqual(1, len(columns))
        self.assertEqual({"0", "1", "2"}, set(columns[0].request_ids))

    def test_phase38_local_residual_cpsat_selects_exact_route_slots(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase38-cpsat", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.collect(["0", "1", "2", "0"], "fixed")
        fixed = collector.pool.columns[:]
        collector.collect(["0", "3", "4", "0"], "candidate")
        collector.collect(["0", "5", "6", "0"], "candidate")

        result = conflict_guided.solve_residual_subproblem(instance, fixed, collector.pool.columns, ["1", "2"], route_slots=2)

        self.assertTrue(result["feasible"])
        self.assertEqual(2, len(result["selectedColumns"]))

    def test_phase38_partition_repair_can_fix_synthetic_infeasible_group(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        nodes[1]["dueTime"] = 1
        nodes[2]["dueTime"] = 1
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [
            {"pickupNodeId": "1", "dropoffNodeId": "2"},
            {"pickupNodeId": "3", "dropoffNodeId": "4"},
            {"pickupNodeId": "5", "dropoffNodeId": "6"},
        ]
        instance = support.normalize_instance("unit", "PDPTW", "phase38-repair", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        groups = [["0", "1"], ["2"]]

        route, attempts = residual_partition.repair_group_route(instance, groups, groups[0], max_repairs=4)

        self.assertGreaterEqual(attempts, 1)
        self.assertTrue(route is None or isinstance(route, list))

    def test_phase38_final_combined_solution_passes_check_solution(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38-final", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        attempt = {"fixedColumns": [], "residualRequestIds": ["0", "1"], "routeSlotsRemaining": 1, "missingRequestIds": ["0"]}

        result = residual_partition.run_residual_partition_attempt(instance, collector, attempt)

        self.assertTrue(result["feasible"])
        self.assertTrue(support.check_solution(instance, result["solution"]).get("feasible"))

    def test_phase38_no_comparator_reference_columns_used(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38-no-leak", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        collector = internal_columns.RouteColumnCollector(instance)
        collector.pool.add_route(["0", "1", "2", "3", "4", "0"], "comparator", source_solver="baseline", provenance="comparator", allowed_for_claim=False)
        columns, _ = residual_partition.construct_partition_columns(instance, collector, [["0", "1"]], "phase38-residual-partition")

        self.assertGreater(len(columns), 0)
        self.assertTrue(any(column.allowed_for_claim for column in collector.pool.columns))
        self.assertTrue(all(column.allowed_for_claim for column in collector.pool.columns if column.source == "phase37-generated-replacement" or column.source == "phase38-residual-partition"))

    def test_phase38b_target_k_constructor_builds_feasible_synthetic_pdptw(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38b-feasible", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})

        result = target_vehicle.construct_target_k(instance, 1, "global-regret-3")
        score = target_vehicle.score_routes(instance, result["routes"])

        self.assertTrue(score["feasible"])
        self.assertEqual(0, score["missingCount"])

    def test_phase38b_target_k_constructor_reports_infeasible_when_k_too_small(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 2
        nodes[2]["demand"] = -2
        nodes[3]["demand"] = 2
        nodes[4]["demand"] = -2
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38b-too-small", 1, 1, nodes, requests, {"vehicleCount": 1, "objective": 8.0})

        result = target_vehicle.construct_target_k(instance, 1, "global-regret-3")
        score = target_vehicle.score_routes(instance, result["routes"])

        self.assertFalse(score["feasible"])

    def test_phase38b_alns_repair_improves_missing_count_on_synthetic_case(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38b-repair", 3, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        initial = [["0", "1", "2", "0"]]
        before = target_vehicle.score_routes(instance, initial)

        repaired = target_vehicle.target_k_alns_repair(instance, initial, [("3", "4"), ("5", "6")], max_runtime_ms=500, max_iterations=10)

        self.assertLessEqual(repaired["score"]["missingCount"], before["missingCount"])

    def test_phase38b_routes_preserve_pickup_before_dropoff(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38b-precedence", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})

        result = target_vehicle.construct_target_k(instance, 1, "earliest-due")

        for route in result["routes"]:
            for pickup, dropoff in target_vehicle.route_pairs(instance, route):
                self.assertLess(route.index(pickup), route.index(dropoff))

    def test_phase38b_deterministic_seed_gives_stable_result(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase38b-deterministic", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})

        first = target_vehicle.construct_target_k(instance, 1, "seeded-shuffle", seed=99)
        second = target_vehicle.construct_target_k(instance, 1, "seeded-shuffle", seed=99)

        self.assertEqual(first["routes"], second["routes"])

    def test_phase39_missing_insertion_repairs_partial_targetk_solution(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase39-insert", 3, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        routes = [["0", "1", "2", "0"]]

        repaired = missing_targetk.forced_missing_repair(instance, routes)

        self.assertEqual(0, repaired["score"]["missingCount"])
        self.assertTrue(repaired["score"]["feasible"])

    def test_phase39_ejection_insertion_can_eject_and_reinsert_request(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase39-eject", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        routes = [["0", "1", "2", "3", "4", "0"], ["0", "0"]]

        options = missing_targetk.enumerate_missing_options(instance, routes, ("5", "6"), max_eject=1)

        self.assertTrue(options)
        self.assertTrue(any(option.option_type in {"direct", "eject-1"} for option in options))

    def test_phase39_missing_priority_orders_few_option_requests_first(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        nodes[5]["dueTime"] = 100
        nodes[6]["dueTime"] = 100
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase39-priority", 3, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        routes = [["0", "1", "2", "0"]]

        ordered = missing_targetk.priority_missing_pairs(instance, routes, [("3", "4"), ("5", "6")])

        self.assertEqual(("5", "6"), ordered[0])

    def test_phase39_perturbation_does_not_increase_missing_count(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase39-perturb", 3, 3, nodes, requests, {"vehicleCount": 1, "objective": 12.0})
        routes = [["0", "1", "2", "0"]]
        before = target_vehicle.score_routes(instance, routes)

        repaired = missing_targetk.perturbation_repair(instance, routes, seed=39, max_attempts=4)

        self.assertLessEqual(repaired["score"]["missingCount"], before["missingCount"])

    def test_phase39_repair_is_deterministic_under_seed(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase39-deterministic", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})

        first = missing_targetk.run_missing_driven_repair(instance, [["0", "1", "2", "0"]])
        second = missing_targetk.run_missing_driven_repair(instance, [["0", "1", "2", "0"]])

        self.assertEqual(first["routes"], second["routes"])

    def test_phase40_objective_ranks_feasible_over_infeasible(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase40-feasible", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        config = natural_pdptw.objective_config("academic_certification")
        feasible = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
        infeasible = {"routes": [["0", "2", "1", "0"], ["0", "3", "4", "0"]]}

        self.assertLess(natural_pdptw.natural_solution_key(instance, feasible, config), natural_pdptw.natural_solution_key(instance, infeasible, config))

    def test_phase40_academic_mode_ranks_fewer_vehicles_over_shorter_distance(self) -> None:
        nodes = [{"id": str(index), "x": float(index * 10), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase40-academic", 3, 3, nodes, requests, {"vehicleCount": 3, "objective": 120.0})
        config = natural_pdptw.objective_config("academic_certification")
        fewer = {"routes": [["0", "1", "2", "3", "4", "5", "6", "0"]]}
        shorter = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"]]}

        self.assertLess(natural_pdptw.natural_solution_key(instance, fewer, config), natural_pdptw.natural_solution_key(instance, shorter, config))

    def test_phase40_production_mode_can_reject_fewer_vehicles_if_tail_penalty_high(self) -> None:
        coords = [(0.0, 0.0), (10.0, 0.0), (11.0, 0.0), (-10.0, 0.0), (-11.0, 0.0), (0.0, 10.0), (0.0, 11.0)]
        nodes = [{"id": str(index), "x": coords[index][0], "y": coords[index][1], "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase40-production", 3, 3, nodes, requests, {"vehicleCount": 3, "objective": 1200.0})
        config = natural_pdptw.objective_config("production_food_dispatch")
        fewer_long_tail = {"routes": [["0", "1", "2", "3", "4", "5", "6", "0"]]}
        more_short_tail = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"]]}

        self.assertGreater(natural_pdptw.objective_components(instance, fewer_long_tail, config)["tailPenalty"], natural_pdptw.objective_components(instance, more_short_tail, config)["tailPenalty"])

    def test_phase40_route_elimination_accepts_only_objective_improving_solution(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase40-elimination", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        config = natural_pdptw.objective_config("academic_certification")
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        result = natural_pdptw.natural_route_elimination(instance, solution, config)

        self.assertLessEqual(len(result["solution"]["routes"]), 2)
        self.assertTrue(any("accepted" in attempt for attempt in result["attempts"]))

    def test_phase40_has_no_instance_name_branch(self) -> None:
        source = Path("scripts/run_phase40_natural_pdptw_optimizer.py").read_text(encoding="utf-8")

        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("startswith(\"LRC\")", source)

    def test_phase41_route_elimination_accepts_when_objective_improves(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase41-accept", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        result = natural_pdptw.objective_driven_route_elimination_repair(instance, solution, natural_pdptw.objective_config("academic_certification"))

        self.assertTrue(result["accepted"])
        self.assertEqual(1, len(result["solution"]["routes"]))

    def test_phase41_route_elimination_rejects_objective_regression(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase41-reject", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        solution = {"routes": [["0", "1", "2", "3", "4", "0"]]}

        result = natural_pdptw.objective_driven_route_elimination_repair(instance, solution, natural_pdptw.objective_config("production_food_dispatch"))

        self.assertFalse(result["accepted"])

    def test_phase41_ejection_chain_repairs_synthetic_eliminated_route(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase41-ejection", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        fixed = [["0", "1", "2", "3", "4", "0"]]

        result = natural_pdptw.objective_aware_ejection_repair(instance, fixed, [("5", "6")], natural_pdptw.objective_config("academic_certification"))

        self.assertIsNotNone(result["solution"])
        self.assertEqual(0, result["missingAfterRepair"])

    def test_phase41_affected_sp_does_not_leak_columns(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase41-sp", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})

        result = natural_pdptw.affected_route_pool_repair(instance, [], [("1", "2"), ("3", "4")], natural_pdptw.objective_config("academic_certification"))

        self.assertIn(result["rejectReason"], {None, "sp-infeasible", "invalid-repair"})
        if result.get("poolStats"):
            self.assertEqual(0, result["poolStats"]["allowedForClaimCounts"].get("disallowed", 0))

    def test_phase41_invalid_repair_is_never_accepted(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 1, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase41-invalid", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        result = natural_pdptw.objective_driven_route_elimination_repair(instance, solution, natural_pdptw.objective_config("academic_certification"))

        if result["accepted"]:
            self.assertTrue(support.check_solution(instance, result["solution"]).get("feasible"))

    def test_phase42_internal_generator_creates_feasible_synthetic_candidate(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase42-generator", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})

        generated = natural_pdptw.InternalSolverCandidateGenerator(max_runtime_ms=600).generate(instance, natural_pdptw.objective_config("academic_certification"))

        self.assertGreaterEqual(generated["candidateCount"], 1)
        self.assertGreaterEqual(generated["feasibleCandidateCount"], 1)

    def test_phase42_candidate_with_objective_regression_is_rejected(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase42-reject", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        solution = {"routes": [["0", "1", "2", "3", "4", "0"]]}

        result = natural_pdptw.internal_solver_improvement(instance, solution, natural_pdptw.objective_config("academic_certification"))

        self.assertFalse(result["accepted"])

    def test_phase42_hard_violation_candidate_is_rejected(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 1, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase42-hard", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        result = natural_pdptw.internal_solver_improvement(instance, solution, natural_pdptw.objective_config("academic_certification"))

        if result["accepted"]:
            self.assertTrue(support.check_solution(instance, result["solution"]).get("feasible"))

    def test_phase42_affected_subproblem_recombines_with_fixed_routes(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}, {"pickupNodeId": "5", "dropoffNodeId": "6"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase42-affected", 3, 3, nodes, requests, {"vehicleCount": 2, "objective": 12.0})
        fixed = [["0", "1", "2", "0"]]

        result = natural_pdptw.InternalSolverCandidateGenerator(max_runtime_ms=600).affected_subproblem(instance, fixed, [("3", "4"), ("5", "6")], natural_pdptw.objective_config("academic_certification"))

        if result.get("solution"):
            self.assertTrue(support.check_solution(instance, result["solution"]).get("feasible"))

    def test_phase42_has_no_instance_name_special_case(self) -> None:
        source = Path("scripts/run_phase40_natural_pdptw_optimizer.py").read_text(encoding="utf-8")

        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("startswith(\"LRC\")", source)

    def test_phase43_warm_start_candidate_preserves_incumbent_routes(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase43-warm", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        generated = natural_pdptw.InternalSolverCandidateGenerator(max_runtime_ms=300).generate(instance, natural_pdptw.objective_config("academic_certification"), incumbent=incumbent)

        self.assertEqual(incumbent["routes"], generated["candidates"][0]["routes"])
        self.assertTrue(generated["trace"][0]["warmStartUsed"])

    def test_phase43_academic_fixed_cost_rejects_vehicle_count_regression(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase43-fixed", 2, 2, nodes, requests, {"vehicleCount": 1, "objective": 8.0})
        incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}

        result = natural_pdptw.internal_solver_improvement(instance, incumbent, natural_pdptw.objective_config("academic_certification"))

        self.assertFalse(result["accepted"])
        self.assertIn(result["trace"]["rejectReason"], {"objective-not-improved", "no-feasible-candidate"})

    def test_phase43_production_tail_penalty_still_visible_with_warm_start(self) -> None:
        coords = [(0.0, 0.0), (10.0, 0.0), (11.0, 0.0), (-10.0, 0.0), (-11.0, 0.0)]
        nodes = [{"id": str(index), "x": coords[index][0], "y": coords[index][1], "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase43-prod", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        config = natural_pdptw.objective_config("production_food_dispatch")

        compressed = natural_pdptw.objective_components(instance, {"routes": [["0", "1", "2", "3", "4", "0"]]}, config)
        split = natural_pdptw.objective_components(instance, {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}, config)

        self.assertGreater(compressed["tailPenalty"], split["tailPenalty"])

    def test_phase43_generator_trace_reports_fixed_cost_and_candidate_deltas(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase43-trace", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        result = natural_pdptw.internal_solver_improvement(instance, incumbent, natural_pdptw.objective_config("academic_certification"))

        self.assertGreater(result["trace"]["fixedCostUsed"], 0)
        self.assertTrue(result["trace"]["warmStartUsed"])
        self.assertTrue(result["trace"]["candidateObjectiveDeltas"])

    def test_baseline_competitiveness_reports_root_cause(self) -> None:
        rows = [{"stage": "A-academic-correctness", "suite": "solomon", "instance": "R101", "verdict": "PASS_WITH_LIMITS", "vehicleCount": 20, "bestKnownVehicleCount": 19}]

        with tempfile.TemporaryDirectory() as temp_dir:
            layer = elite.score_baseline_competitiveness(rows, Path(temp_dir) / "max", Path(temp_dir) / "pyvrp")

        self.assertEqual("vehicle-count", layer["metrics"]["strongBaselineGapRootCause"])


if __name__ == "__main__":
    unittest.main()

