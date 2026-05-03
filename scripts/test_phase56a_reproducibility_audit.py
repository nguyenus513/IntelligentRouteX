from __future__ import annotations

import unittest

from run_phase56a_reproducibility_audit import classify_reproducibility


def row(
    after: int,
    *,
    before: int = 5,
    objective_improved: bool = True,
    signature: str = "sig-a",
    route_pool_skipped: bool = False,
    accepted: bool = True,
) -> dict:
    stages = [
        {"name": "natural-route-elimination", "skipped": False, "skippedReason": None},
        {"name": "route-pool-sp", "skipped": route_pool_skipped, "skippedReason": "insufficient-budget" if route_pool_skipped else None},
    ]
    return {
        "instance": "LRC202",
        "vehicleCountBefore": before,
        "vehicleCountAfter": after,
        "vehicleCountImproved": after < before,
        "objectiveImproved": objective_improved,
        "operatorTrace": {"naturalRouteElimination": {"acceptedByBudgetedRunner": accepted}},
        "stageRuntimeSummary": {"overBudget": False, "stages": stages},
        "solutionSignature": signature,
    }


class Phase56AReproducibilityAuditTest(unittest.TestCase):
    def test_detects_nondeterministic_outcome_distribution(self) -> None:
        baseline = row(4, signature="baseline")
        runs = [row(4, signature="sig-a"), row(5, objective_improved=False, signature="sig-b")]

        result = classify_reproducibility(baseline, runs)

        self.assertEqual("nondeterministic-runner", result["classification"])

    def test_detects_deterministic_regression(self) -> None:
        baseline = row(4, signature="baseline")
        runs = [row(5, objective_improved=True, signature="same"), row(5, objective_improved=True, signature="same")]

        result = classify_reproducibility(baseline, runs)

        self.assertEqual("deterministic-regression", result["classification"])

    def test_detects_budget_starvation_from_skipped_route_pool(self) -> None:
        baseline = row(4, signature="baseline")
        runs = [row(5, signature="same", route_pool_skipped=True), row(5, signature="same", route_pool_skipped=True)]

        result = classify_reproducibility(baseline, runs)

        self.assertEqual("budget-starvation", result["classification"])

    def test_detects_baseline_mismatch(self) -> None:
        baseline = row(4, signature="baseline", accepted=False)
        runs = [row(5, signature="same"), row(5, signature="same")]

        result = classify_reproducibility(baseline, runs)

        self.assertEqual("baseline-artifact-stale", result["classification"])


if __name__ == "__main__":
    unittest.main()

