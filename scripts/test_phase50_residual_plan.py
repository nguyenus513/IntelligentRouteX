from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_phase50_residual_pass_with_limits_plan import action_for_classifications, run
from run_phase50_residual_pass_with_limits_plan import write_json


def diagnostics(instance: str, verdict: str, trace: dict | None = None) -> dict:
    return {
        "instance": instance,
        "verdict": verdict,
        "vehicleCountBefore": 3,
        "vehicleCountAfter": 3,
        "runtimeMs": 100,
        "hardViolations": 0,
        "leakageDetected": False,
        "stageRuntimeSummary": {"overBudget": False, "stages": []},
        "operatorTrace": trace or {},
    }


class Phase50ResidualPlanTest(unittest.TestCase):
    def test_planner_selects_only_pass_with_limits_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase47 = root / "phase47"
            phase46 = root / "phase46"
            for name, verdict in (("a", "PASS_WITH_LIMITS"), ("b", "PASS_STRONG")):
                write_json(phase47 / name / "diagnostics.json", diagnostics(name, verdict, {"stage": {"rejectReason": "candidate-cap"}}))
            write_json(phase46 / "per_instance_classification.json", {"instances": [{"instance": "a", "classifications": ["candidate-cap"], "primaryClassification": "candidate-cap"}]})

            summary = run(phase47, phase46, root / "out")

            self.assertEqual(1, summary["residualCaseCount"])
            self.assertEqual("a", summary["residualPlans"][0]["instance"])

    def test_candidate_cap_maps_to_fast_neighborhood_action(self) -> None:
        action = action_for_classifications(["candidate-cap"], [])

        self.assertEqual("candidate-cap", action["blockerCategory"])
        self.assertEqual("fast-neighborhood-cap-profile", action["phase51Target"])

    def test_route_count_skip_maps_to_bounded_large_route_action(self) -> None:
        action = action_for_classifications(["route-count-too-large-skip"], [])

        self.assertEqual("route-count-too-large-skip", action["blockerCategory"])
        self.assertEqual("bounded-large-route-elimination-profile", action["phase51Target"])

    def test_objective_not_improved_maps_to_no_objective_change(self) -> None:
        action = action_for_classifications(["feasible-candidate-rejected-by-objective"], ["objective-not-improved"])

        self.assertEqual("objective-protected", action["blockerCategory"])
        self.assertEqual("no-objective-change", action["phase51Target"])

    def test_gate_fails_for_unknown_residual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase47 = root / "phase47"
            phase46 = root / "phase46"
            write_json(phase47 / "a" / "diagnostics.json", diagnostics("a", "PASS_WITH_LIMITS"))
            write_json(phase46 / "per_instance_classification.json", {"instances": []})

            summary = run(phase47, phase46, root / "out")

            self.assertEqual("FAIL", summary["gateVerdict"])
            self.assertEqual(1, summary["unknownCount"])

    def test_plan_contains_no_target_k_production_recommendation(self) -> None:
        action = action_for_classifications(["candidate-cap"], [])

        self.assertNotIn("target-k production", action["recommendedAction"].lower())


if __name__ == "__main__":
    unittest.main()
