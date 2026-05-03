from __future__ import annotations

import unittest
from pathlib import Path

import external_benchmark_support as support
from run_phase47_adaptive_budget_natural_optimizer import adaptive_budget_profile, bounded_large_route_elimination, fast_incumbent_neighborhood_repair
from run_phase40_natural_pdptw_optimizer import objective_components, objective_config


class Phase47AdaptiveBudgetTest(unittest.TestCase):
    def test_adaptive_profile_prioritizes_internal_generator_for_infeasible_incumbent(self) -> None:
        profile = adaptive_budget_profile({"routeCount": 0, "requestCount": 10, "incumbentFeasible": False, "timeWindowTightness": 0.1, "mixedness": 1.0}, 30_000)

        self.assertTrue(profile["stages"]["internal-solver-generator"]["enabled"])
        self.assertGreaterEqual(profile["stages"]["internal-solver-generator"]["preferredMs"], 4_500)
        self.assertFalse(profile["stages"]["natural-route-elimination"]["enabled"])

    def test_large_route_count_uses_bounded_large_elimination_not_old_stage(self) -> None:
        profile = adaptive_budget_profile({"routeCount": 20, "requestCount": 40, "incumbentFeasible": True, "timeWindowTightness": 0.1, "mixedness": 1.0}, 30_000)

        self.assertFalse(profile["stages"]["natural-route-elimination"]["enabled"])
        self.assertTrue(profile["stages"]["bounded-large-route-elimination"]["enabled"])

    def test_fast_neighborhood_respects_affected_request_cap(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": str(pickup), "dropoffNodeId": str(dropoff)} for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]]
        instance = support.normalize_instance("unit", "PDPTW", "phase47-fast-neighborhood", 4, 4, nodes, requests, {"vehicleCount": 4, "objective": 20.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"], ["0", "7", "8", "0"]]}

        result = fast_incumbent_neighborhood_repair(instance, solution, objective_config("academic_certification"), max_runtime_ms=300)

        self.assertTrue(result["fastMode"])
        self.assertEqual(8, result["maxAffectedRequestCap"])

    def test_bounded_large_elimination_never_accepts_objective_regression(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": str(pickup), "dropoffNodeId": str(dropoff)} for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]]
        instance = support.normalize_instance("unit", "PDPTW", "phase47-no-regression", 3, 3, nodes, requests, {"vehicleCount": 3, "objective": 12.0})
        solution = {"routes": [["0", "1", "2", "3", "4", "5", "6", "0"]]}
        config = objective_config("academic_certification")

        result = bounded_large_route_elimination(instance, solution, config, max_runtime_ms=200)

        self.assertFalse(result["accepted"])
        self.assertLessEqual(objective_components(instance, result["solution"], config)["objective"], objective_components(instance, solution, config)["objective"])

    def test_phase47_has_no_instance_name_branch(self) -> None:
        source = Path("scripts/run_phase47_adaptive_budget_natural_optimizer.py").read_text(encoding="utf-8")

        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("startswith(\"LRC\")", source)


if __name__ == "__main__":
    unittest.main()
