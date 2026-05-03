from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import run_phase56b_stable_promoted_runner as phase56b
from run_phase45_budgeted_natural_pdptw_optimizer import StageBudgetScheduler


def tiny_instance() -> dict:
    return {
        "nodes": [{"id": str(index)} for index in range(5)],
        "distanceMatrix": [[0, 1, 1, 1, 1] for _ in range(5)],
        "requests": [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}],
    }


class Phase56BStablePromotedRunnerTest(unittest.TestCase):
    def test_optional_stage_skipped_when_it_would_starve_route_pool(self) -> None:
        scheduler = StageBudgetScheduler(30_000, reserve_ms=3_000)
        scheduler.started_at -= 25.0
        policy = phase56b.StableBudgetPolicy(routePoolReserveMs=5_000, finalReserveMs=3_000)

        self.assertFalse(phase56b.can_start_optional_stage(scheduler, policy, 700, route_pool_pending=True))

    def test_route_pool_reserve_is_preserved_before_optional_stage(self) -> None:
        scheduler = StageBudgetScheduler(30_000, reserve_ms=3_000)
        scheduler.started_at -= 18.0
        policy = phase56b.StableBudgetPolicy(routePoolReserveMs=5_000, finalReserveMs=3_000)

        self.assertTrue(phase56b.can_start_optional_stage(scheduler, policy, 700, route_pool_pending=True))

    def test_natural_route_guard_is_feature_based(self) -> None:
        scheduler = StageBudgetScheduler(30_000, reserve_ms=3_000)
        policy = phase56b.StableBudgetPolicy(routePoolReserveMs=5_000, finalReserveMs=3_000)
        features = {"routeCount": 5, "requestCount": 51}

        guard = phase56b.stable_natural_route_elimination_guard(features, [2, 12, 15], scheduler, policy)

        self.assertEqual("run", guard["decision"])

    def test_no_instance_name_branch(self) -> None:
        source = inspect.getsource(phase56b)

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("startswith('LRC')", source)
        self.assertNotIn("instanceName ==", source)

    def test_gate_rejects_objective_regression(self) -> None:
        rows = [
            {
                "verdict": "PASS",
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 101.0,
                "stageRuntimeSummary": {"overBudget": False},
            }
        ]

        gate = phase56b.phase56b_gate(rows)

        self.assertEqual("FAIL", gate["verdict"])
        self.assertFalse(gate["checks"]["noAcceptedObjectiveRegression"])

    def test_gate_rejects_duplicate_instance_instability(self) -> None:
        rows = [
            {
                "instance": "LRC202",
                "verdict": "PASS",
                "vehicleCountBefore": 5,
                "vehicleCountAfter": 5,
                "objectiveImproved": True,
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 90.0,
                "stageRuntimeSummary": {"overBudget": False},
            },
            {
                "instance": "LRC202",
                "verdict": "PASS_STRONG",
                "vehicleCountBefore": 5,
                "vehicleCountAfter": 4,
                "objectiveImproved": True,
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 80.0,
                "stageRuntimeSummary": {"overBudget": False},
            },
        ]

        gate = phase56b.phase56b_gate(rows)

        self.assertEqual("FAIL", gate["verdict"])
        self.assertFalse(gate["checks"]["duplicateOutcomesStable"])

    def test_duplicate_final_signatures_pass(self) -> None:
        rows = [
            {
                "instance": "LRC202",
                "verdict": "PASS_STRONG",
                "vehicleCountBefore": 5,
                "vehicleCountAfter": 4,
                "objectiveImproved": True,
                "finalSolutionSignature": "same",
                "routePoolRan": True,
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 80.0,
                "stageRuntimeSummary": {"overBudget": False},
            },
            {
                "instance": "LRC202",
                "verdict": "PASS_STRONG",
                "vehicleCountBefore": 5,
                "vehicleCountAfter": 4,
                "objectiveImproved": True,
                "finalSolutionSignature": "same",
                "routePoolRan": True,
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 80.0,
                "stageRuntimeSummary": {"overBudget": False},
            },
        ]

        gate = phase56b.phase56b_gate(rows)

        self.assertEqual("PASS", gate["verdict"])

    def test_different_final_signatures_fail(self) -> None:
        rows = [
            {
                "instance": "LRC202",
                "verdict": "PASS_STRONG",
                "vehicleCountBefore": 5,
                "vehicleCountAfter": 4,
                "objectiveImproved": True,
                "finalSolutionSignature": "left",
                "routePoolRan": True,
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 80.0,
                "stageRuntimeSummary": {"overBudget": False},
            },
            {
                "instance": "LRC202",
                "verdict": "PASS_STRONG",
                "vehicleCountBefore": 5,
                "vehicleCountAfter": 4,
                "objectiveImproved": True,
                "finalSolutionSignature": "right",
                "routePoolRan": True,
                "hardViolations": 0,
                "leakageDetected": False,
                "routePoolSkipReason": None,
                "objectiveBefore": 100.0,
                "objectiveAfter": 80.0,
                "stageRuntimeSummary": {"overBudget": False},
            },
        ]

        gate = phase56b.phase56b_gate(rows)

        self.assertEqual("FAIL", gate["verdict"])
        self.assertFalse(gate["checks"]["duplicateFinalSignaturesStable"])

    def test_stable_incumbent_replay_reuses_cached_incumbent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "incumbent.json"
            solution = {"routes": [["0", "2", "1", "0"], ["0", "4", "3", "0"]]}
            instance = tiny_instance()

            phase56b.save_incumbent_cache(cache_path, instance, solution)
            loaded = phase56b.load_incumbent_cache(cache_path)

            self.assertEqual(phase56b.solution_signature(instance, solution), phase56b.solution_signature(instance, loaded))

    def test_deterministic_sort_is_stable_for_equal_objective_candidates(self) -> None:
        instance = tiny_instance()
        routes = [["0", "4", "3", "0"], ["0", "2", "1", "0"]]

        sorted_once = sorted(routes, key=lambda route: phase56b.stable_route_sort_key(instance, route))
        sorted_twice = sorted(reversed(routes), key=lambda route: phase56b.stable_route_sort_key(instance, route))

        self.assertEqual(sorted_once, sorted_twice)


if __name__ == "__main__":
    unittest.main()
