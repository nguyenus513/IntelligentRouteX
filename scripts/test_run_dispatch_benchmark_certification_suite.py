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


if __name__ == "__main__":
    unittest.main()
