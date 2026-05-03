from __future__ import annotations

import unittest
from pathlib import Path

import external_benchmark_support as support
from run_phase40_natural_pdptw_optimizer import _exact_pair_coverage, objective_components, objective_config
from run_phase52_population_natural_optimizer import RouteSetPopulationGenerator, add_individual, make_individual, recombine_route_sets


def tiny_instance() -> dict:
    nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(7)]
    for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]:
        nodes[pickup]["demand"] = 1
        nodes[dropoff]["demand"] = -1
    requests = [{"pickupNodeId": str(pickup), "dropoffNodeId": str(dropoff)} for pickup, dropoff in [(1, 2), (3, 4), (5, 6)]]
    return support.normalize_instance("unit", "PDPTW", "phase52-pop", 3, 3, nodes, requests, {"vehicleCount": 3, "objective": 12.0})


class Phase52PopulationOptimizerTest(unittest.TestCase):
    def test_recombination_preserves_exact_request_coverage(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        parent_a = make_individual(instance, {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "5", "6", "0"]]}, config, "a")
        parent_b = make_individual(instance, {"routes": [["0", "1", "2", "3", "4", "0"], ["0", "5", "6", "0"]]}, config, "b")

        child = recombine_route_sets(instance, parent_a, parent_b, config)

        self.assertIsNotNone(child)
        self.assertTrue(_exact_pair_coverage(instance, child)["valid"])

    def test_duplicate_request_coverage_is_rejected_or_repaired(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        duplicate = {"routes": [["0", "1", "2", "0"], ["0", "1", "2", "3", "4", "5", "6", "0"]]}

        individual = make_individual(instance, duplicate, config, "bad")

        self.assertIsNone(individual)

    def test_population_diversity_rejects_duplicate_signatures(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "5", "6", "0"]]}
        population = []
        duplicate_rejections = {"count": 0}

        add_individual(population, make_individual(instance, solution, config, "a"), 4, duplicate_rejections)
        add_individual(population, make_individual(instance, solution, config, "b"), 4, duplicate_rejections)

        self.assertEqual(1, len(population))
        self.assertEqual(1, duplicate_rejections["count"])

    def test_objective_regression_not_accepted(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        current = {"routes": [["0", "1", "2", "3", "4", "5", "6", "0"]]}
        worse = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"]]}

        result = RouteSetPopulationGenerator(max_runtime_ms=200, max_recombination_attempts=2).improve(instance, current, config, [("worse", worse)])

        self.assertFalse(result["accepted"])
        self.assertLessEqual(objective_components(instance, result["solution"], config)["objective"], objective_components(instance, current, config)["objective"])

    def test_source_has_no_instance_name_or_comparator_reference_bks(self) -> None:
        source = Path("scripts/run_phase52_population_natural_optimizer.py").read_text(encoding="utf-8")

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("ortools-baseline", source)
        self.assertNotIn("BKS", source)
        self.assertNotIn("reference", source.lower())


if __name__ == "__main__":
    unittest.main()
