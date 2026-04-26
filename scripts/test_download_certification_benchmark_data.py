from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "download_certification_benchmark_data.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("download_certification_benchmark_data", MODULE_PATH)
downloader = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = downloader
assert SPEC.loader is not None
SPEC.loader.exec_module(downloader)


class DownloadCertificationBenchmarkDataTest(unittest.TestCase):
    def test_file_entry_includes_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "file.txt"
            path.write_text("abc", encoding="utf-8")

            entry = downloader.file_entry(path, "https://example.test/file.txt")

        self.assertEqual("sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", entry["sha256"])
        self.assertEqual(3, entry["bytes"])
        self.assertEqual("https://example.test/file.txt", entry["url"])

    def test_homberger_manifest_reports_missing_official_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = downloader.write_homberger_manifest(root)
            missing_path = Path(entry["missingPath"])
            payload = downloader.json.loads(missing_path.read_text(encoding="utf-8"))

        self.assertEqual("official-only", payload["policy"])
        self.assertEqual("EVIDENCE_GAP", payload["verdict"])
        self.assertIn("C1_2_1.txt", payload["missingFiles"])


if __name__ == "__main__":
    unittest.main()
