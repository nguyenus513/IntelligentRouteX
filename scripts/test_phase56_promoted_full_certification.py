from __future__ import annotations

import unittest

from run_phase56_promoted_full_certification import aggregate, classify_regressions, gate


def row(
    name: str,
    before: int,
    after: int,
    *,
    verdict: str = "PASS_WITH_LIMITS",
    hard: int = 0,
    over: bool = False,
    leakage: bool = False,
    objective_before: float = 1000.0,
    objective_after: float | None = None,
    distance_after: float = 100.0,
) -> dict:
    if objective_after is None:
        objective_after = 900.0 if after < before else objective_before
    return {
        "instance": name,
        "verdict": verdict,
        "vehicleCountBefore": before,
        "vehicleCountAfter": after,
        "vehicleCountImproved": after < before,
        "distanceBefore": 110.0,
        "distanceAfter": distance_after,
        "objectiveBefore": objective_before,
        "objectiveAfter": objective_after,
        "objectiveImproved": objective_after < objective_before,
        "hardViolations": hard,
        "leakageDetected": leakage,
        "runtimeMs": 100,
        "stageRuntimeSummary": {"overBudget": over},
    }


class Phase56PromotedFullCertificationTest(unittest.TestCase):
    def test_gate_detects_hard_violation(self) -> None:
        summary = {"aggregate": aggregate([row("A", 5, 4, hard=1)])}

        result = gate(summary, [])

        self.assertEqual("FAIL", result["verdict"])
        self.assertFalse(result["checks"]["hardViolationsZero"])

    def test_gate_detects_over_budget(self) -> None:
        summary = {"aggregate": aggregate([row("A", 5, 4, over=True)])}

        result = gate(summary, [])

        self.assertEqual("FAIL", result["verdict"])
        self.assertFalse(result["checks"]["overBudgetZero"])

    def test_detects_regression_on_previously_improved_case(self) -> None:
        baseline = {"a": row("A", 14, 12)}
        current = {"a": row("A", 14, 13)}

        regressions = classify_regressions(current, baseline, distance_tolerance=0.01, objective_tolerance=0.0)

        self.assertIn("previously-improved-vehicle-regression", {item["type"] for item in regressions})

    def test_gate_passes_clean_promoted_summary(self) -> None:
        rows = [row("A", 5, 4), row("B", 10, 10)]
        summary = {"aggregate": aggregate(rows)}

        result = gate(summary, [])

        self.assertEqual("PASS", result["verdict"])

    def test_detects_accepted_objective_regression(self) -> None:
        summary = {"aggregate": aggregate([row("A", 5, 4, objective_after=1001.0)])}

        result = gate(summary, [])

        self.assertEqual("FAIL", result["verdict"])
        self.assertFalse(result["checks"]["noAcceptedObjectiveRegression"])


if __name__ == "__main__":
    unittest.main()

