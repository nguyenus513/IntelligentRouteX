from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from parse_li_lim_pdptw import parse_li_lim
from parse_solomon_vrptw import parse_solomon

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "community-phase9-inventory"
SUITES = {
    "solomon": {
        "path": REPO_ROOT / "benchmarks" / "external" / "official" / "solomon",
        "parser": parse_solomon,
        "problemType": "VRPTW",
    },
    "li-lim": {
        "path": REPO_ROOT / "benchmarks" / "external" / "official" / "li-lim-pdptw",
        "parser": parse_li_lim,
        "problemType": "PDPTW",
    },
    "homberger": {
        "path": REPO_ROOT / "benchmarks" / "external" / "official" / "homberger",
        "parser": None,
        "problemType": "VRPTW_SCALE",
    },
}


def inspect_instance(path: Path, parser: Callable[[Path], dict[str, Any]] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "instance": path.stem,
        "path": str(path),
        "parseStatus": "DEFERRED" if parser is None else "UNKNOWN",
        "problemType": "",
        "nodeCount": 0,
        "requestCount": 0,
        "bestKnownVehicleCount": None,
        "bestKnownDistance": None,
        "error": "",
    }
    if parser is None:
        row["error"] = "parser-not-wired-for-phase9-smoke"
        return row
    try:
        normalized = parser(path)
    except Exception as exception:  # pragma: no cover - inventory must report, not crash.
        row["parseStatus"] = "FAIL"
        row["error"] = f"{type(exception).__name__}: {exception}"
        return row
    best_known = normalized.get("bestKnown", {})
    row.update({
        "parseStatus": "PASS",
        "problemType": normalized.get("problemType", ""),
        "nodeCount": len(normalized.get("nodes", [])),
        "requestCount": len(normalized.get("requests", [])),
        "bestKnownVehicleCount": best_known.get("vehicleCount"),
        "bestKnownDistance": best_known.get("objective"),
    })
    return row


def build_inventory() -> dict[str, Any]:
    suites: list[dict[str, Any]] = []
    for suite_name, config in SUITES.items():
        root = config["path"]
        files = sorted(root.glob("*.txt")) if root.exists() else []
        rows = [inspect_instance(path, config["parser"]) for path in files]
        status_counts = Counter(row["parseStatus"] for row in rows)
        suites.append({
            "suite": suite_name,
            "path": str(root),
            "problemType": config["problemType"],
            "fileCount": len(files),
            "parseStatusCounts": dict(sorted(status_counts.items())),
            "sampleInstances": [row["instance"] for row in rows[:10]],
            "rows": rows,
        })
    blockers = []
    for suite in suites:
        if suite["suite"] in {"solomon", "li-lim"} and suite["parseStatusCounts"].get("PASS", 0) == 0:
            blockers.append(f"phase9-inventory-no-parseable-{suite['suite']}")
    return {
        "schemaVersion": "phase9-official-inventory/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "suites": suites,
        "blockers": blockers,
        "pass": not blockers,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 9 Official Benchmark Inventory",
        "",
        f"- verdict: `{'PASS' if report['pass'] else 'FAIL'}`",
        f"- blockers: `{report['blockers']}`",
        "",
        "| Suite | Type | Files | Parse Counts | Samples |",
        "|---|---|---:|---|---|",
    ]
    for suite in report["suites"]:
        lines.append(
            f"| {suite['suite']} | {suite['problemType']} | {suite['fileCount']} | "
            f"{suite['parseStatusCounts']} | {suite['sampleInstances']} |"
        )
    lines.extend([
        "",
        "## Phase 9 Scope",
        "",
        "Solomon and Li & Lim are enabled for official/auto smoke and core certification. Homberger is inventoried but deferred until a dedicated scale parser/runner is wired into the certification rail.",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory official community benchmark assets for Phase 9.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    report = build_inventory()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "official_inventory.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "official_inventory.md").write_text(markdown(report), encoding="utf-8")
    print(f"[PHASE9 INVENTORY] wrote {output_dir}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
