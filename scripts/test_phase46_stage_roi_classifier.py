from __future__ import annotations

import unittest

from run_phase46_stage_roi_classifier import classify_instance, stage_roi


def diagnostic(trace: dict, stages: list[dict] | None = None, objective_improved: bool = False) -> dict:
    return {
        "instance": "unit",
        "verdict": "PASS_WITH_LIMITS",
        "runtimeMs": 100,
        "vehicleCountBefore": 2,
        "vehicleCountAfter": 2,
        "objectiveBefore": 20.0,
        "objectiveAfter": 20.0,
        "objectiveImproved": objective_improved,
        "hardViolations": 0,
        "leakageDetected": False,
        "operatorTrace": trace,
        "stageRuntimeSummary": {"overBudget": False, "stages": stages or []},
    }


class Phase46StageRoiClassifierTest(unittest.TestCase):
    def test_classifier_detects_route_count_too_large_skip(self) -> None:
        row = diagnostic(
            {"naturalRouteElimination": {"skipped": True, "skippedReason": "route-count-too-large-for-unbounded-stage"}},
            [{"name": "natural-route-elimination", "runtimeMs": 0, "skipped": True, "skippedReason": "route-count-too-large-for-unbounded-stage"}],
        )

        classified = classify_instance(row)

        self.assertIn("route-count-too-large-skip", classified["classifications"])

    def test_classifier_detects_objective_not_improved_with_feasible_candidate(self) -> None:
        row = diagnostic({"internalSolverGenerator": {"feasibleCandidateCount": 2, "budgetedRejectReason": "objective-not-improved"}})

        classified = classify_instance(row)

        self.assertIn("feasible-candidate-rejected-by-objective", classified["classifications"])

    def test_classifier_detects_candidate_cap(self) -> None:
        row = diagnostic({"incumbentNeighborhoodRepair": {"trace": [{"rejectReason": "candidate-cap"}]}})

        classified = classify_instance(row)

        self.assertIn("candidate-cap", classified["classifications"])

    def test_roi_summary_counts_stage_acceptances(self) -> None:
        rows = [
            diagnostic(
                {"internalSolverGenerator": {"accepted": True, "feasibleCandidateCount": 3}},
                [{"name": "internal-solver-generator", "runtimeMs": 20, "skipped": False}],
                objective_improved=True,
            ),
            diagnostic(
                {"internalSolverGenerator": {"accepted": False, "feasibleCandidateCount": 1, "budgetedRejectReason": "objective-not-improved"}},
                [{"name": "internal-solver-generator", "runtimeMs": 40, "skipped": False}],
            ),
        ]

        roi = stage_roi(rows)

        self.assertEqual(1, roi["internalSolverGenerator"]["acceptedCount"])
        self.assertEqual(4, roi["internalSolverGenerator"]["generatedFeasibleCandidateCount"])
        self.assertEqual(1, roi["internalSolverGenerator"]["objectiveImprovementCount"])
        self.assertEqual(30.0, roi["internal-solver-generator"]["averageRuntimeMs"])


if __name__ == "__main__":
    unittest.main()
