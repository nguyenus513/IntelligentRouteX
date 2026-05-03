from __future__ import annotations

import inspect
import unittest

import run_phase56d_stable_stage_audit as phase56d
from run_phase40_natural_pdptw_optimizer import objective_config


def tiny_instance() -> dict:
    return {
        "depotNodeId": "0",
        "capacity": 10,
        "nodes": [
            {"id": "0", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 0},
            {"id": "1", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "2", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
            {"id": "3", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 1},
            {"id": "4", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": -1},
        ],
        "distanceMatrix": [[0, 1, 1, 1, 1] for _ in range(5)],
        "requests": [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}],
    }


def audit_row(instance: str, *, internal: str = "i", route_pool: str = "r", accepted: tuple[str, ...] = ("internalSolverGenerator",), final: str = "f", over: bool = False) -> dict:
    return {
        "instance": instance,
        "vehicleCountBefore": 5,
        "vehicleCountAfter": 4,
        "objectiveBefore": 100.0,
        "objectiveAfter": 90.0,
        "hardViolations": 0,
        "overBudget": over,
        "finalSolutionSignature": final,
        "acceptedStages": list(accepted),
        "stageCandidateAudit": [
            {"stage": "internalSolverGenerator", "candidateSignature": internal},
            {"stage": "routePoolImprovement", "candidateSignature": route_pool},
        ],
    }


class Phase56DStableStageAuditTest(unittest.TestCase):
    def test_stable_candidate_key_tie_breaks_by_signature(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        left = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
        right = {"routes": [["0", "3", "4", "0"], ["0", "1", "2", "0"]]}

        self.assertEqual(phase56d.stable_candidate_key(instance, left, config), phase56d.stable_candidate_key(instance, right, config))

    def test_deterministic_accept_rejects_objective_regression(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        current = {"routes": [["0", "1", "3", "4", "2", "0"]]}
        worse = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

        _, accepted, reason, _ = phase56d.deterministic_accept(instance, current, worse, config)

        self.assertFalse(accepted)
        self.assertEqual("objective-not-improved", reason)

    def test_deterministic_accept_is_stable_for_equal_objective_candidates(self) -> None:
        instance = tiny_instance()
        config = objective_config("academic_certification")
        current = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
        equal = {"routes": [["0", "3", "4", "0"], ["0", "1", "2", "0"]]}

        _, accepted, reason, audit = phase56d.deterministic_accept(instance, current, equal, config)

        self.assertFalse(accepted)
        self.assertEqual("objective-not-improved", reason)
        self.assertEqual(audit["candidateStableKey"], audit["currentStableKey"])

    def test_classifier_detects_internal_generator_nondeterministic(self) -> None:
        rows = [audit_row("A", internal="one"), audit_row("A", internal="two")]

        result = phase56d.classify_stage_audit(rows)

        self.assertEqual("internal-generator-nondeterministic", result["classification"])

    def test_classifier_detects_route_pool_nondeterministic(self) -> None:
        rows = [audit_row("A", internal="same", route_pool="one"), audit_row("A", internal="same", route_pool="two")]

        result = phase56d.classify_stage_audit(rows)

        self.assertEqual("route-pool-nondeterministic", result["classification"])

    def test_classifier_detects_accept_order_nondeterministic(self) -> None:
        rows = [audit_row("A", internal="same", route_pool="same", accepted=("internalSolverGenerator",)), audit_row("A", internal="same", route_pool="same", accepted=("routePoolImprovement",))]

        result = phase56d.classify_stage_audit(rows)

        self.assertEqual("accept-order-nondeterministic", result["classification"])

    def test_no_instance_name_branch(self) -> None:
        source = inspect.getsource(phase56d)

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("startswith('LRC')", source)
        self.assertNotIn("instanceName ==", source)


if __name__ == "__main__":
    unittest.main()

