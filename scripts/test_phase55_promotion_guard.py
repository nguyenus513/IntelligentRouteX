from __future__ import annotations

import unittest

from run_phase55_promotion_guard import guard


def row(
    name: str,
    before: int,
    after: int,
    *,
    objective_after: float | None = None,
    verdict: str = "PASS_WITH_LIMITS",
    hard: int = 0,
    over: bool = False,
    leakage: bool = False,
) -> dict:
    objective_before = 1000.0
    if objective_after is None:
        objective_after = 900.0 if after < before else objective_before
    return {
        "instance": name,
        "verdict": verdict,
        "vehicleCountBefore": before,
        "vehicleCountAfter": after,
        "vehicleCountImproved": after < before,
        "objectiveBefore": objective_before,
        "objectiveAfter": objective_after,
        "objectiveImproved": objective_after < objective_before,
        "hardViolations": hard,
        "leakageDetected": leakage,
        "stageRuntimeSummary": {"overBudget": over},
    }


class Phase55PromotionGuardTest(unittest.TestCase):
    def test_rejects_lower_total_vehicle_reduction(self) -> None:
        baseline = {"a": row("A", 5, 4), "b": row("B", 10, 9)}
        candidate = {"a": row("A", 5, 4), "b": row("B", 10, 10)}

        summary = guard(baseline, candidate, "candidate")

        self.assertEqual("DIAGNOSTIC_ONLY", summary["verdict"])
        self.assertFalse(summary["checks"]["vehicleReductionAtLeastBaseline"])
        self.assertIn("total-vehicle-reduction-regression", {failure["type"] for failure in summary["failures"]})

    def test_rejects_regression_on_baseline_improved_case(self) -> None:
        baseline = {"a": row("A", 14, 12), "b": row("B", 5, 5)}
        candidate = {"a": row("A", 14, 13), "b": row("B", 5, 4)}

        summary = guard(baseline, candidate, "candidate")

        self.assertEqual("DIAGNOSTIC_ONLY", summary["verdict"])
        self.assertFalse(summary["checks"]["noBaselineImprovedCaseRegression"])
        self.assertIn("per-instance-vehicle-regression", {failure["type"] for failure in summary["failures"]})

    def test_rejects_hard_violation_over_budget_and_leakage(self) -> None:
        baseline = {"a": row("A", 5, 4), "b": row("B", 6, 5), "c": row("C", 7, 6)}
        candidate = {
            "a": row("A", 5, 4, hard=1),
            "b": row("B", 6, 5, over=True),
            "c": row("C", 7, 6, leakage=True),
        }

        summary = guard(baseline, candidate, "candidate")

        self.assertEqual("DIAGNOSTIC_ONLY", summary["verdict"])
        self.assertFalse(summary["checks"]["hardViolationsZero"])
        self.assertFalse(summary["checks"]["overBudgetZero"])
        self.assertFalse(summary["checks"]["leakageZero"])

    def test_accepts_same_safety_and_better_vehicle_reduction(self) -> None:
        baseline = {"a": row("A", 5, 4), "b": row("B", 10, 10)}
        candidate = {"a": row("A", 5, 4), "b": row("B", 10, 8)}

        summary = guard(baseline, candidate, "candidate")

        self.assertEqual("PROMOTE_CANDIDATE", summary["verdict"])

    def test_rejects_missing_baseline_instance(self) -> None:
        baseline = {"a": row("A", 5, 4), "b": row("B", 10, 10)}
        candidate = {"a": row("A", 5, 4)}

        summary = guard(baseline, candidate, "candidate")

        self.assertEqual("DIAGNOSTIC_ONLY", summary["verdict"])
        self.assertFalse(summary["checks"]["candidateCoversBaselineInstances"])
        self.assertIn("missing-baseline-instance", {failure["type"] for failure in summary["failures"]})


if __name__ == "__main__":
    unittest.main()

