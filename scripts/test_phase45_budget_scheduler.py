from __future__ import annotations

import time
import unittest

from run_phase45_budgeted_natural_pdptw_optimizer import StageBudgetScheduler, _stage_call


class Phase45BudgetSchedulerTest(unittest.TestCase):
    def test_stage_budget_respects_reserve(self) -> None:
        scheduler = StageBudgetScheduler(total_budget_ms=1_000, reserve_ms=200)

        budget = scheduler.stage_budget("heavy", preferred_ms=900, min_ms=100)

        self.assertLessEqual(budget, 800)
        self.assertGreaterEqual(budget, 100)

    def test_stage_call_skips_when_budget_too_low(self) -> None:
        scheduler = StageBudgetScheduler(total_budget_ms=100, reserve_ms=90)
        calls = []

        result = _stage_call(
            scheduler,
            "expensive-stage",
            preferred_ms=80,
            min_ms=50,
            call=lambda budget: calls.append(budget) or {"solution": {}},
        )

        self.assertIsNone(result)
        self.assertEqual([], calls)
        self.assertTrue(scheduler.stages[-1]["skipped"])
        self.assertEqual("budget-too-low", scheduler.stages[-1]["skippedReason"])

    def test_stage_call_records_runtime_for_executed_stage(self) -> None:
        scheduler = StageBudgetScheduler(total_budget_ms=1_000, reserve_ms=100)

        result = _stage_call(
            scheduler,
            "cheap-stage",
            preferred_ms=100,
            min_ms=10,
            call=lambda budget: {"budgetSeen": budget},
        )

        self.assertIsNotNone(result)
        self.assertIn("budgetSeen", result)
        self.assertFalse(scheduler.stages[-1]["skipped"])
        self.assertEqual("cheap-stage", scheduler.stages[-1]["name"])
        self.assertGreaterEqual(scheduler.stages[-1]["runtimeMs"], 0)

    def test_summary_reports_over_budget(self) -> None:
        scheduler = StageBudgetScheduler(total_budget_ms=1, reserve_ms=0)
        time.sleep(0.01)

        summary = scheduler.summary()

        self.assertTrue(summary["overBudget"])
        self.assertGreater(summary["totalRuntimeMs"], summary["totalBudgetMs"])


if __name__ == "__main__":
    unittest.main()
