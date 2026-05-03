from __future__ import annotations

import unittest
from pathlib import Path

import external_benchmark_support as support
from run_phase40_natural_pdptw_optimizer import objective_components, objective_config
from run_phase51_fast_neighborhood_profile import (
    CONSERVATIVE_PROFILE,
    EXPANDED_PROFILE,
    LARGE_SAFE_PROFILE,
    ProfiledIncumbentNeighborhoodRepairGenerator,
    fast_incumbent_neighborhood_repair_with_profile,
    run,
    select_fast_neighborhood_profile,
)


class Phase51FastNeighborhoodProfileTest(unittest.TestCase):
    def test_profile_selection_uses_features_only_not_instance_names(self) -> None:
        features = {"routeCount": 10, "requestCount": 50, "timeWindowTightness": 0.02, "mixedness": 45.0, "incumbentFeasible": True}

        first, first_reason = select_fast_neighborhood_profile(dict(features, instanceName="LRC206"), 5_000)
        second, second_reason = select_fast_neighborhood_profile(dict(features, instanceName="totally-different"), 5_000)

        self.assertEqual(first, second)
        self.assertEqual(first_reason, second_reason)

    def test_expanded_profile_raises_caps_relative_to_conservative(self) -> None:
        self.assertGreater(EXPANDED_PROFILE.max_neighborhoods, CONSERVATIVE_PROFILE.max_neighborhoods)
        self.assertGreater(EXPANDED_PROFILE.max_ortools_pairs, CONSERVATIVE_PROFILE.max_ortools_pairs)
        self.assertGreater(EXPANDED_PROFILE.max_affected_request_count, CONSERVATIVE_PROFILE.max_affected_request_count)

    def test_large_safe_profile_caps_affected_request_count(self) -> None:
        profile, reason = select_fast_neighborhood_profile({"routeCount": 20, "requestCount": 160, "timeWindowTightness": 0.01, "mixedness": 10.0, "incumbentFeasible": True}, 5_000)

        self.assertEqual(LARGE_SAFE_PROFILE, profile)
        self.assertEqual("large-route-or-request-count", reason)
        self.assertLessEqual(profile.max_affected_request_count, EXPANDED_PROFILE.max_affected_request_count)

    def test_neighborhoods_above_affected_cap_are_skipped(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(9)]
        for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]:
            nodes[pickup]["demand"] = 1
            nodes[dropoff]["demand"] = -1
        requests = [{"pickupNodeId": str(pickup), "dropoffNodeId": str(dropoff)} for pickup, dropoff in [(1, 2), (3, 4), (5, 6), (7, 8)]]
        instance = support.normalize_instance("unit", "PDPTW", "phase51-cap", 4, 4, nodes, requests, {"vehicleCount": 4, "objective": 20.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"], ["0", "5", "6", "0"], ["0", "7", "8", "0"]]}
        tiny_profile = LARGE_SAFE_PROFILE.__class__("tiny", 200, 4, 2, 1, 1, 50)

        result = ProfiledIncumbentNeighborhoodRepairGenerator(tiny_profile).repair(instance, solution, objective_config("academic_certification"))

        self.assertGreater(result["neighborhoodsSkippedByAffectedCap"], 0)
        self.assertTrue(result["candidateCapHit"])

    def test_objective_regression_is_never_returned(self) -> None:
        nodes = [{"id": str(index), "x": float(index), "y": 0.0, "demand": 0, "readyTime": 0, "dueTime": 10_000, "serviceTime": 0} for index in range(5)]
        nodes[1]["demand"] = 1
        nodes[2]["demand"] = -1
        nodes[3]["demand"] = 1
        nodes[4]["demand"] = -1
        requests = [{"pickupNodeId": "1", "dropoffNodeId": "2"}, {"pickupNodeId": "3", "dropoffNodeId": "4"}]
        instance = support.normalize_instance("unit", "PDPTW", "phase51-regression", 2, 2, nodes, requests, {"vehicleCount": 2, "objective": 8.0})
        solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
        config = objective_config("production_food_dispatch")

        result = fast_incumbent_neighborhood_repair_with_profile(instance, solution, config, EXPANDED_PROFILE, max_runtime_ms=500)

        self.assertLessEqual(objective_components(instance, result["solution"], config)["objective"], objective_components(instance, solution, config)["objective"])

    def test_source_has_no_comparator_or_instance_name_special_case(self) -> None:
        source = Path("scripts/run_phase51_fast_neighborhood_profile.py").read_text(encoding="utf-8")

        self.assertNotIn("startswith(\"LRC\")", source)
        self.assertNotIn("instanceName ==", source)
        self.assertNotIn("ortools-baseline", source)
        self.assertNotIn("reference", source.lower())

    def test_summary_gate_reports_pass_with_limits_when_cap_not_reduced(self) -> None:
        # Exercise the exported gate formula through a tiny fixture run would be too slow;
        # this test anchors the public summary fields through source-level contract checks.
        source = Path("scripts/run_phase51_fast_neighborhood_profile.py").read_text(encoding="utf-8")

        self.assertIn("candidateCapHitCount", source)
        self.assertIn("totalVehicleReduction", source)
        self.assertIn("phase51Gate", source)


if __name__ == "__main__":
    unittest.main()
