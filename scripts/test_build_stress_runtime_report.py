import json
import tempfile
import unittest
from pathlib import Path

import build_stress_runtime_report as stress_report


def artifact(scenario="normal-clear", size="M", baseline="A", selector_timeout=False, repair_timeout=False, fallbacks=0, cap_loss=0.0):
    return {
        "scenarioPack": scenario,
        "workloadSize": size,
        "baselineId": baseline,
        "selectorTelemetry": {
            "timedOut": selector_timeout,
            "fallbackLevel": "CP_SAT_TIMEOUT_INCUMBENT" if selector_timeout else "NONE",
            "poolInputCount": 160,
            "poolReducedCount": 160,
            "poolRejectedCount": 0,
            "selectorPoolCapApplied": False,
            "selectorPoolCapObjectiveLoss": cap_loss,
        },
        "activeRepair": {"timedOut": repair_timeout, "runtimeMs": 12 if repair_timeout else 0, "operatorsTried": 2},
        "stageFallbackSummary": {"totalFallbacks": fallbacks},
        "metrics": {"selectedProposalCount": 1, "executedAssignmentCount": 1},
    }


class BuildStressRuntimeReportTest(unittest.TestCase):
    def test_passes_clean_runtime_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-normal-clear-m-legacy-v2-controlled-a.json").write_text(json.dumps(artifact()), encoding="utf-8")
            report = stress_report.summarize(stress_report.load_rows(root), ["normal-clear"])

        self.assertTrue(report["pass"])
        self.assertEqual(0, report["selectorTimeoutCount"])
        self.assertEqual(0, report["fallbackRowCount"])

    def test_fails_on_true_runtime_bottleneck(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-traffic-shock-l-legacy-v2-controlled-a.json").write_text(
                json.dumps(artifact("traffic-shock", "L", selector_timeout=True, fallbacks=1)),
                encoding="utf-8",
            )
            report = stress_report.summarize(stress_report.load_rows(root), ["traffic-shock"])

        self.assertFalse(report["pass"])
        self.assertEqual(1, report["selectorTimeoutCount"])
        self.assertEqual(1, report["fallbackRowCount"])
        self.assertEqual(1, len(report["badRows"]))

    def test_missing_expected_scenario_is_pass_with_limits_not_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-normal-clear-m-legacy-v2-controlled-a.json").write_text(json.dumps(artifact()), encoding="utf-8")
            report = stress_report.summarize(stress_report.load_rows(root), ["normal-clear", "worker-degradation"])

        self.assertTrue(report["pass"])
        self.assertTrue(report["passWithLimits"])
        self.assertEqual(["worker-degradation"], report["missingExpectedScenarios"])


if __name__ == "__main__":
    unittest.main()
