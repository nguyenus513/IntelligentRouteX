from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "verify_certification_dataset.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("verify_certification_dataset", MODULE_PATH)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)


class VerifyCertificationDatasetTest(unittest.TestCase):
    def touch(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok", encoding="utf-8")

    def seed_smoke_dataset(self, root: Path) -> None:
        for instance in ("C101", "R101", "RC101"):
            self.touch(root / "solomon" / f"{instance}.txt")
        for instance in ("LC101", "LR101", "LRC101"):
            self.touch(root / "li-lim-pdptw" / f"{instance}.txt")
        for instance in ("C1_2_1", "R1_2_1", "RC1_2_1"):
            self.touch(root / "homberger" / f"{instance}.txt")
        for instance in checker.MDRP_SMOKE:
            for filename in checker.MDRP_REQUIRED_FILES:
                self.touch(root / "mdrplib" / instance / filename)
        self.touch(root / "icaps-dpdp" / "factory_info.csv")
        for index in (1, 2):
            self.touch(root / "icaps-dpdp" / f"icaps-case-{index}" / f"50_{index}.csv")
            self.touch(root / "icaps-dpdp" / f"icaps-case-{index}" / "vehicle_info_5.csv")

    def test_smoke_dataset_ready_without_required_hcm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "official"
            self.seed_smoke_dataset(root)
            payload = checker.build_readiness("smoke", root, Path(temp_dir) / "full-system", False)

        self.assertTrue(payload["datasetReady"])
        self.assertEqual(0, payload["counts"]["MISSING_REQUIRED"])
        self.assertGreater(payload["counts"]["MISSING_OPTIONAL"], 0)

    def test_core_reports_missing_required_benchmark_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "official"
            self.seed_smoke_dataset(root)
            payload = checker.build_readiness("core", root, Path(temp_dir) / "full-system", True)

        missing_items = {item["item"] for item in payload["blockers"]}
        self.assertFalse(payload["datasetReady"])
        self.assertIn("solomon/C201", missing_items)
        self.assertIn("li-lim-pdptw/LC201", missing_items)
        self.assertIn("mdrp-core-4/couriers.txt", missing_items)
        self.assertIn("normal-clear/S/full-system", missing_items)


if __name__ == "__main__":
    unittest.main()
