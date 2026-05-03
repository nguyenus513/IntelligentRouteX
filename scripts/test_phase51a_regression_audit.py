from __future__ import annotations

import unittest

from run_phase51a_lrc202_regression_audit import first_divergence


def diagnostics(stages: list[dict], trace: dict | None = None) -> dict:
    return {
        "schemaVersion": "unit",
        "instance": "LRC202",
        "vehicleCountBefore": 5,
        "vehicleCountAfter": 4,
        "objectiveBefore": 10.0,
        "objectiveAfter": 8.0,
        "runtimeMs": 100,
        "stageRuntimeSummary": {"stages": stages},
        "operatorTrace": trace or {},
    }


class Phase51ARegressionAuditTest(unittest.TestCase):
    def test_identifies_accepted_vs_rejected_divergence(self) -> None:
        stages = [{"name": "internal-solver-generator", "runtimeMs": 10, "skipped": False}]
        left = diagnostics(stages, {"internalSolverGenerator": {"acceptedByBudgetedRunner": True}})
        right = diagnostics(stages, {"internalSolverGenerator": {"acceptedByBudgetedRunner": False}})

        divergence = first_divergence(left, right)

        self.assertEqual("accepted-vs-rejected", divergence["type"])
        self.assertEqual("internal-solver-generator", divergence["stage"])

    def test_identifies_budget_starvation_divergence(self) -> None:
        left = diagnostics([{"name": "natural-route-elimination", "runtimeMs": 200, "skipped": False}])
        right = diagnostics([{"name": "natural-route-elimination", "runtimeMs": 2_000, "skipped": False}])

        divergence = first_divergence(left, right)

        self.assertEqual("budget-starvation", divergence["type"])

    def test_identifies_missing_stage_divergence(self) -> None:
        left = diagnostics([{"name": "route-pool-sp", "runtimeMs": 100, "skipped": False}])
        right = diagnostics([])

        divergence = first_divergence(left, right)

        self.assertEqual("missing-stage", divergence["type"])
        self.assertEqual("route-pool-sp", divergence["stage"])


if __name__ == "__main__":
    unittest.main()
