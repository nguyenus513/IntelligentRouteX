from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_benchmark_certification_suite.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("run_dispatch_benchmark_certification_suite", MODULE_PATH)
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
assert SPEC.loader is not None
SPEC.loader.exec_module(runner)


class DispatchBenchmarkCertificationSuiteTest(unittest.TestCase):
    def test_generated_dpdp_stress_row_passes(self) -> None:
        row = runner.generated_dpdp_row("dynamic-stress", "dpdp-stress", 3, 5)

        self.assertEqual("PASS", row["verdict"])
        self.assertEqual(3, row["servedOrderCount"])

    def test_evidence_gap_makes_final_pass_with_limits(self) -> None:
        rows = [
            {"verdict": "PASS"},
            {"verdict": "EVIDENCE_GAP"},
        ]

        self.assertEqual("PASS_WITH_LIMITS", runner.certification_verdict(rows))

    def test_suite_writes_smoke_stage_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.run_suite("our-dispatch-v2", 30_000, Path(temp_dir), "smoke")

        self.assertEqual(16, len(result["results"]))
        self.assertIn("A-academic-correctness", {row["stage"] for row in result["results"]})
        self.assertIn("E-hcm-road-native", {row["stage"] for row in result["results"]})
        self.assertIn(result["finalVerdict"], {"PASS", "PASS_WITH_LIMITS", "FAIL"})

    def test_mdrplib_row_uses_official_smoke_data_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            row = runner.mdrp_row("mdrp-smoke-low", "low", Path(temp_dir))

        self.assertIn(row["verdict"], {"PASS_WITH_LIMITS", "EVIDENCE_GAP"})
        if row["verdict"] != "EVIDENCE_GAP":
            self.assertEqual(0, row["pickupBeforeReadyTimeViolation"])
            self.assertEqual(0, row["courierShiftViolation"])

    def test_icaps_row_uses_official_smoke_data_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            row = runner.icaps_row("icaps-case-1", Path(temp_dir))

        self.assertIn(row["verdict"], {"PASS_WITH_LIMITS", "EVIDENCE_GAP"})
        if row["verdict"] != "EVIDENCE_GAP":
            self.assertEqual(0, row["timeWindowViolationCount"])
            self.assertEqual(0, row["activeRouteCorruptionCount"])
            self.assertEqual(0, row["vehicleStateContinuityViolation"])
            self.assertGreaterEqual(row["routeStabilityScore"], 0.99)
            self.assertIn("maxReplanLatencyMs", row)


    def test_main_emit_scorecard_writes_scorecard_outputs(self) -> None:
        original_run_suite = runner.run_suite
        try:
            runner.run_suite = lambda solver, time_limit_ms, output_root, level: {
                "schemaVersion": "dispatch-benchmark-certification-suite/v1",
                "level": level,
                "solver": solver,
                "results": [{
                    "stage": "D-dynamic-stress",
                    "verdict": "PASS",
                    "runtimeMs": 0,
                    "rail": "dynamic-stress",
                    "suite": "dpdp-stress",
                    "instance": "unit",
                    "solver": solver,
                    "feasible": True,
                }],
                "verdictCounts": {"PASS": 1, "PASS_WITH_LIMITS": 0, "FAIL": 0, "EVIDENCE_GAP": 0},
                "finalVerdict": "PASS",
            }
            with tempfile.TemporaryDirectory() as temp_dir:
                exit_code = runner.main(["--output-root", temp_dir, "--emit-scorecard"])
                root = Path(temp_dir)
                self.assertEqual(0, exit_code)
                self.assertTrue((root / "certification_scorecard.json").exists())
                self.assertTrue((root / "certification_scorecard.md").exists())
        finally:
            runner.run_suite = original_run_suite
if __name__ == "__main__":
    unittest.main()
