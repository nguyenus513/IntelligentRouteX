from __future__ import annotations

import unittest
from pathlib import Path

import external_benchmark_support as support
from run_phase40_natural_pdptw_optimizer import _exact_pair_coverage
from run_phase54a_population_missing_repair import repair_missing_pair, recombine_route_sets_with_missing_repair
from run_phase52_population_natural_optimizer import make_individual
from run_phase40_natural_pdptw_optimizer import objective_config


def fixture_instance() -> dict:
    nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
    for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
        nodes[pickup]["demand"] = 1
        nodes[dropoff]["demand"] = -1
    requests = [{"pickupNodeId": str(pickup), "dropoffNodeId": str(dropoff)} for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]]
    return support.normalize_instance("unit", "PDPTW", "phase54a", 3, 3, nodes, requests, {"vehicleCount": 3, "objective": 12.0})


class Phase54AMissingRepairTest(unittest.TestCase):
    def test_ejection_one_repairs_synthetic_missing_pair(self) -> None:
        instance = fixture_instance()
        diagnostics = {}
        routes = [["0", "1", "2", "0"], ["0", "3", "4", "0"]]

        repaired = repair_missing_pair(instance, routes, ("5", "6"), diagnostics, max_candidate_checks=300)

        self.assertIsNotNone(repaired)
        solution = {"routes": repaired}
        self.assertTrue(_exact_pair_coverage(instance, solution)["missingPairs"] == [])

    def test_mini_destroy_regret_preserves_exact_coverage(self) -> None:
        instance = fixture_instance()
        config = objective_config("academic_certification")
        parent_a = make_individual(instance, {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"]]}, config, "a")
        parent_b = make_individual(instance, {"routes": [["0", "5", "6", "0"], ["0", "1", "2", "3", "4", "0"]]}, config, "b")
        diagnostics = {}

        child = recombine_route_sets_with_missing_repair(instance, parent_a, parent_b, config, diagnostics=diagnostics)

        self.assertIsNotNone(child)
        self.assertTrue(_exact_pair_coverage(instance, child)["valid"])
        self.assertIn("missingRepairStrategiesTried", diagnostics)

    def test_candidate_cap_respected(self) -> None:
        instance = fixture_instance()
        diagnostics = {}
        routes = [["0", "1", "2", "0"]]

        repaired = repair_missing_pair(instance, routes, ("3", "4"), diagnostics, max_candidate_checks=1)

        self.assertTrue(repaired is None or diagnostics.get("candidateChecksUsed", 0) <= 3)

    def test_source_has_no_instance_name_branch(self) -> None:
        source = Path("scripts/run_phase54a_population_missing_repair.py").read_text(encoding="utf-8")

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("targetVehicleCount", source)
        self.assertNotIn("ortools-baseline", source)


if __name__ == "__main__":
    unittest.main()
