import json
import tempfile
import unittest
from pathlib import Path

import build_full_optimizer_report as full_report


def academic(strong_gap=0.0, vehicle_gap=0):
    return {
        "schemaVersion": "solver-gap-report/v1",
        "vehicle_count_gap": vehicle_gap,
        "distance_gap_pct": 0.0,
        "duration_gap_pct": 0.0,
        "served_order_gap": 0,
        "feasibility_delta": 0.0,
        "runtime_to_best_ms": 12,
        "strong_baseline_gap": strong_gap,
    }


def ablation():
    return {
        "schemaVersion": "dispatch-optimizer-ablation/v1",
        "bestVariantId": "A5",
        "mlValueClaim": False,
        "variants": [
            {"variantId": f"A{index}", "status": "disabled-by-policy" if index >= 6 else "enabled", "qualityScore": 1.0 + index, "fallbackRate": 0.02, "mlValueClaim": False}
            for index in range(9)
        ],
    }


def ablation_baseline_fallback_only():
    payload = ablation()
    for variant in payload["variants"]:
        if variant["variantId"] == "A0":
            variant["fallbackRate"] = 0.12
        elif variant["variantId"] == "A5":
            variant["fallbackRate"] = 0.07
        elif variant["status"] == "enabled":
            variant["fallbackRate"] = 0.08
    return payload


class BuildFullOptimizerReportTest(unittest.TestCase):
    def test_builds_report_from_complete_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            academic_path = root / "academic.json"
            ablation_path = root / "ablation.json"
            academic_path.write_text(json.dumps(academic()), encoding="utf-8")
            ablation_path.write_text(json.dumps(ablation()), encoding="utf-8")
            output_dir = root / "report"

            self.assertEqual(0, full_report.main(["--academic-report", str(academic_path), "--ablation-results", str(ablation_path), "--output-dir", str(output_dir)]))
            payload = json.loads((output_dir / "full_optimizer_report.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "full_optimizer_report.md").read_text(encoding="utf-8")

        self.assertEqual("full-optimizer-report/v1", payload["schemaVersion"])
        self.assertTrue(payload["bottlenecks"])
        self.assertIn("nextRecommendation", payload)
        self.assertIn("## Bottleneck Ranking", markdown)

    def test_missing_optional_input_does_not_crash_and_marks_gate_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "report"
            self.assertEqual(0, full_report.main(["--academic-report", str(Path(temp_dir) / "missing.json"), "--output-dir", str(output_dir)]))
            payload = json.loads((output_dir / "full_optimizer_report.json").read_text(encoding="utf-8"))

        self.assertTrue(payload["missingInputs"])
        self.assertFalse(payload["gates"]["academicBridgePass"])
        self.assertFalse(payload["gates"]["ablationPass"])

    def test_high_academic_gap_creates_high_bottleneck(self) -> None:
        payload = full_report.build_report(academic(strong_gap=0.2, vehicle_gap=1), ablation(), None, [])
        first = payload["bottlenecks"][0]

        self.assertEqual("academic-gap", first["component"])
        self.assertEqual("HIGH", first["severity"])

    def test_ml_disabled_policy_prevents_ml_value_claim(self) -> None:
        payload = full_report.build_report(academic(), ablation(), None, [])

        self.assertTrue(payload["gates"]["llmDisabled"])
        self.assertFalse(payload["quality"]["mlValueClaim"])
        self.assertTrue(any(item["component"] == "ml" and item["severity"] == "LOW" for item in payload["bottlenecks"]))

    def test_dispatch_runtime_profile_surfaces_selector_and_repair_timeouts(self) -> None:
        dispatch = json.dumps({
            "selectorTelemetry": {
                "timedOut": True,
                "fallbackLevel": "CP_SAT_TIMEOUT_INCUMBENT",
                "poolInputCount": 400,
                "poolReducedCount": 256,
                "poolRejectedCount": 144,
                "selectorMaxPoolSize": 256,
                "selectorPoolCapApplied": True,
                "selectorPoolCapObjectiveLoss": 0.0,
            },
            "activeRepair": {"timedOut": True, "runtimeMs": 301, "operatorsTried": 99},
        })

        payload = full_report.build_report(academic(), ablation(), dispatch, [])
        components = {item["component"] for item in payload["bottlenecks"]}

        self.assertIn("selector-runtime", components)
        self.assertIn("repair-runtime", components)
        self.assertTrue(payload["runtime"]["profile"]["selectorTimedOut"])
        self.assertTrue(payload["runtime"]["profile"]["repairTimedOut"])

    def test_pool_reducer_bottleneck_requires_objective_loss(self) -> None:
        dispatch = json.dumps({
            "selectorTelemetry": {
                "selectorPoolCapApplied": True,
                "selectorPoolCapObjectiveLoss": 0.25,
            }
        })

        payload = full_report.build_report(academic(), ablation(), dispatch, [])

        self.assertTrue(any(item["component"] == "pool-reducer" for item in payload["bottlenecks"]))

    def test_runtime_bottleneck_uses_current_best_variant_not_a0_max(self) -> None:
        payload = full_report.build_report(academic(), ablation_baseline_fallback_only(), None, [])
        runtime = next(item for item in payload["bottlenecks"] if item["component"] == "runtime")

        self.assertEqual("LOW", runtime["severity"])
        self.assertEqual(0.07, payload["runtime"]["currentFallbackRate"])
        self.assertEqual(0.12, payload["runtime"]["maxFallbackRate"])
        self.assertEqual("A5", payload["runtime"]["currentVariantId"])
        self.assertIn("no blocking bottleneck", payload["nextRecommendation"])


if __name__ == "__main__":
    unittest.main()
