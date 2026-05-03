import json
import tempfile
import unittest
from pathlib import Path

import build_optimizer_ablation_report as report_builder
import run_dispatch_optimizer_ablation as ablation


class RunDispatchOptimizerAblationTest(unittest.TestCase):
    def test_ablation_writes_a0_to_a8_and_disables_ml_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            self.assertEqual(0, ablation.main(["--scenario-pack", "normal-clear", "--size", "S", "--output-dir", str(output_dir)]))
            payload = json.loads((output_dir / "ablation_results.json").read_text(encoding="utf-8"))
            report_path = output_dir / "ablation_report.md"
            self.assertEqual(0, report_builder.main(["--input", str(output_dir / "ablation_results.json"), "--output", str(report_path)]))
            report = report_path.read_text(encoding="utf-8")

        variants = {variant["variantId"]: variant for variant in payload["variants"]}
        self.assertEqual({f"A{index}" for index in range(9)}, set(variants))
        self.assertTrue(all(variants[key]["status"] == "disabled-by-policy" for key in ("A6", "A7", "A8")))
        self.assertFalse(payload["mlValueClaim"])
        self.assertIn("| A5 | CP-SAT/set packing selector | enabled |", report)
        self.assertIn("A6-A8 disabled-by-policy", report)


if __name__ == "__main__":
    unittest.main()
