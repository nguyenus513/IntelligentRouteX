from __future__ import annotations

from scripts.build_phase9_official_inventory import build_inventory, main


def test_inventory_finds_parseable_official_suites() -> None:
    report = build_inventory()

    assert report["pass"] is True
    suites = {suite["suite"]: suite for suite in report["suites"]}
    assert suites["solomon"]["parseStatusCounts"].get("PASS", 0) > 0
    assert suites["li-lim"]["parseStatusCounts"].get("PASS", 0) > 0


def test_inventory_cli_writes_outputs(tmp_path) -> None:
    assert main(["--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "official_inventory.json").exists()
    assert (tmp_path / "official_inventory.md").exists()
