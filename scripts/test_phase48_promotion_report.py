from __future__ import annotations

import unittest

from run_phase48_promotion_report import aggregate, recommend_runner


def row(vehicles_after: int, *, verdict: str = "PASS_WITH_LIMITS", hard: int = 0, over: bool = False, objective: bool = False, runtime: int = 100) -> dict:
    return {
        "verdict": verdict,
        "vehicleCountBefore": 10,
        "vehicleCountAfter": vehicles_after,
        "objectiveBefore": 1000.0,
        "objectiveAfter": 900.0 if objective else 1000.0,
        "objectiveImproved": objective,
        "vehicleCountImproved": vehicles_after < 10,
        "hardViolations": hard,
        "leakageDetected": False,
        "runtimeMs": runtime,
        "stageRuntimeSummary": {"overBudget": over},
    }


class Phase48PromotionReportTest(unittest.TestCase):
    def test_promotion_chooses_phase47_when_vehicle_reduction_improves_same_safety(self) -> None:
        phase45 = aggregate({"a": row(9, verdict="PASS_STRONG", objective=True)})
        phase47 = aggregate({"a": row(8, verdict="PASS_STRONG", objective=True, runtime=120)})

        recommendation = recommend_runner(phase45, phase47)

        self.assertEqual("phase47", recommendation["promotedRunner"])

    def test_promotion_rejects_phase47_with_fail(self) -> None:
        phase45 = aggregate({"a": row(9, verdict="PASS_STRONG", objective=True)})
        phase47 = aggregate({"a": row(8, verdict="FAIL", objective=True)})

        recommendation = recommend_runner(phase45, phase47)

        self.assertEqual("phase45", recommendation["promotedRunner"])

    def test_promotion_rejects_phase47_with_hard_violation(self) -> None:
        phase45 = aggregate({"a": row(9, verdict="PASS_STRONG", objective=True)})
        phase47 = aggregate({"a": row(8, verdict="PASS_STRONG", hard=1, objective=True)})

        recommendation = recommend_runner(phase45, phase47)

        self.assertEqual("phase45", recommendation["promotedRunner"])

    def test_promotion_rejects_phase47_with_over_budget(self) -> None:
        phase45 = aggregate({"a": row(9, verdict="PASS_STRONG", objective=True)})
        phase47 = aggregate({"a": row(8, verdict="PASS_STRONG", over=True, objective=True)})

        recommendation = recommend_runner(phase45, phase47)

        self.assertEqual("phase45", recommendation["promotedRunner"])


if __name__ == "__main__":
    unittest.main()
