from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "build_certification_scorecard.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("build_certification_scorecard", MODULE_PATH)
scorecard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scorecard
assert SPEC.loader is not None
SPEC.loader.exec_module(scorecard)


class CertificationScorecardTest(unittest.TestCase):
    def write_results(self, root: Path, rows: list[dict]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "certification_suite_results.json").write_text(
            json.dumps({"finalVerdict": "PASS_WITH_LIMITS", "results": rows}),
            encoding="utf-8",
        )

    def layer(self, built: dict, name: str) -> dict:
        return next(layer for layer in built["layers"] if layer["layer"] == name)

    def test_vehicle_count_gap_routes_to_academic_consolidation(self) -> None:
        rows = [{
            "stage": "A-academic-correctness",
            "verdict": "PASS_WITH_LIMITS",
            "vehicleCount": 12,
            "bestKnownVehicleCount": 10,
            "objectiveGapPercent": 5.0,
            "capacityViolationCount": 0,
            "timeWindowViolationCount": 0,
            "pickupBeforeDropoffViolationCount": 0,
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_results(root, rows)
            built = scorecard.build_scorecard(root)

        academic = self.layer(built, "academic-correctness")
        self.assertEqual("vehicle-count-gap", academic["mainBlocker"])
        self.assertEqual("academic-global-consolidation", academic["recommendedLane"])
        self.assertEqual("PASS_WITH_LIMITS", academic["verdict"])

    def test_homberger_evidence_gap_routes_to_data_closure(self) -> None:
        rows = [{
            "stage": "B-scale",
            "verdict": "EVIDENCE_GAP",
            "verdictReasons": ["homberger-official-instance-missing"],
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_results(root, rows)
            built = scorecard.build_scorecard(root)

        scale = self.layer(built, "academic-scale")
        self.assertEqual("evidence-gap", scale["mainBlocker"])
        self.assertEqual("data-closure", scale["recommendedLane"])
        self.assertEqual("EVIDENCE_GAP", scale["verdict"])

    def test_hcm_route_fallback_and_zero_coverage_are_blockers(self) -> None:
        rows = [{
            "stage": "E-hcm-road-native",
            "verdict": "PASS_WITH_LIMITS",
            "coveredOrderCount": 0,
            "executedAssignmentCount": 0,
            "routeFallbackRate": 0.5,
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_results(root, rows)
            built = scorecard.build_scorecard(root)

        hcm = self.layer(built, "hcm-road-native")
        self.assertIn("hcm-coverage-zero", hcm["blockers"])
        self.assertIn("hcm-assignment-zero", hcm["blockers"])
        self.assertIn("route-fallback-used", hcm["blockers"])
        self.assertEqual("hcm-plan-selection", hcm["recommendedLane"])

    def test_native_greedrl_preflight_is_not_lite_blocker(self) -> None:
        rows = [{
            "stage": "E-hcm-road-native",
            "verdict": "PASS",
            "coveredOrderCount": 20,
            "executedAssignmentCount": 5,
            "routeFallbackRate": 0.0,
            "workerFallbackRate": 0.0,
            "greedrlRuntimeMode": "native",
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "certification-suite"
            self.write_results(root, rows)
            full_system = Path(temp_dir) / "full-system-e2e"
            full_system.mkdir()
            (full_system / "preflight_result.json").write_text(json.dumps({
                "verdict": "PASS",
                "workers": {"workers": [{
                    "name": "greedrl",
                    "ready": True,
                    "version": {"runtimeMode": "native"},
                }]},
            }), encoding="utf-8")
            built = scorecard.build_scorecard(root, full_system)

        hcm = self.layer(built, "hcm-road-native")
        self.assertNotIn("greedrl-lite-runtime", hcm["blockers"])
        self.assertEqual("PASS", hcm["verdict"])

    def test_mdrplib_baseline_only_routes_to_food_objective_lane(self) -> None:
        rows = [{
            "stage": "C-food-delivery-official",
            "verdict": "PASS_WITH_LIMITS",
            "servedOrderRate": 1.0,
            "lateOrderRate": 0.0,
            "verdictReasons": ["mdrplib-official-structural-baseline"],
            "pickupBeforeReadyTimeViolation": 0,
            "courierShiftViolation": 0,
            "foodOnVehicleHardViolation": 0,
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_results(root, rows)
            built = scorecard.build_scorecard(root)

        food = self.layer(built, "food-delivery-public")
        self.assertEqual("food-baseline-only", food["mainBlocker"])
        self.assertEqual("food-delivery-objective", food["recommendedLane"])

    def test_icaps_baseline_only_routes_to_dynamic_replan_lane(self) -> None:
        rows = [{
            "stage": "D-dynamic-official",
            "verdict": "PASS_WITH_LIMITS",
            "routeStabilityScore": 1.0,
            "maxReplanLatencyMs": 10,
            "verdictReasons": ["icaps-deterministic-rolling-horizon-baseline"],
            "activeRouteCorruptionCount": 0,
            "vehicleStateContinuityViolation": 0,
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_results(root, rows)
            built = scorecard.build_scorecard(root)

        dynamic = self.layer(built, "dynamic-dispatch")
        self.assertEqual("dynamic-baseline-only", dynamic["mainBlocker"])
        self.assertEqual("dynamic-replan-policy", dynamic["recommendedLane"])


if __name__ == "__main__":
    unittest.main()
