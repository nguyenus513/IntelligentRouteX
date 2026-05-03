from __future__ import annotations

import unittest
from pathlib import Path

from run_phase51b_budget_protected_profile import RESERVED_ROUTE_POOL_BUDGET_MS, natural_route_elimination_guard


class Phase51BBudgetProtectionTest(unittest.TestCase):
    def test_guard_skips_when_route_pool_budget_would_be_starved(self) -> None:
        guard = natural_route_elimination_guard({"routeCount": 5, "requestCount": 50}, [2, 3, 4], remaining_ms=5_000, reserve_needed_ms=5_000)

        self.assertEqual("skip", guard["decision"])
        self.assertEqual("route-pool-budget-protected", guard["reason"])

    def test_guard_allows_when_route_count_and_smallest_route_are_safe(self) -> None:
        guard = natural_route_elimination_guard({"routeCount": 5, "requestCount": 50}, [2, 3, 4], remaining_ms=15_000, reserve_needed_ms=7_000)

        self.assertEqual("run", guard["decision"])
        self.assertEqual("predicted-safe", guard["reason"])

    def test_guard_skips_large_route_count_for_bounded_stage(self) -> None:
        guard = natural_route_elimination_guard({"routeCount": 20, "requestCount": 80}, [1, 2, 3], remaining_ms=20_000, reserve_needed_ms=7_000)

        self.assertEqual("skip", guard["decision"])
        self.assertEqual("large-route-count-uses-bounded-stage", guard["reason"])

    def test_route_pool_minimum_budget_constant_is_preserved(self) -> None:
        self.assertGreaterEqual(RESERVED_ROUTE_POOL_BUDGET_MS, 5_000)

    def test_source_has_no_instance_name_branch(self) -> None:
        source = Path("scripts/run_phase51b_budget_protected_profile.py").read_text(encoding="utf-8")

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("targetVehicleCount", source)
        self.assertNotIn("ortools-baseline", source)


if __name__ == "__main__":
    unittest.main()
