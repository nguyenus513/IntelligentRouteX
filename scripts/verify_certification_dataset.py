from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "benchmarks" / "external" / "official"
DEFAULT_FULL_SYSTEM_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "full-system-e2e"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "certification-suite"

ACADEMIC_SMOKE = {
    "solomon": ["C101", "R101", "RC101"],
    "li-lim-pdptw": ["LC101", "LR101", "LRC101"],
}
ACADEMIC_CORE = {
    "solomon": ["C101", "C201", "R101", "R201", "RC101", "RC201"],
    "li-lim-pdptw": ["LC101", "LC201", "LR101", "LR201", "LRC101", "LRC201"],
}
HOMBERGER_SMOKE = ["C1_2_1", "R1_2_1", "RC1_2_1"]
HOMBERGER_CORE = [
    "C1_2_1", "R1_2_1", "RC1_2_1",
    "C1_4_1", "R1_4_1", "RC1_4_1",
    "C1_6_1", "R1_6_1", "RC1_6_1",
    "C1_8_1", "R1_8_1", "RC1_8_1",
    "C1_10_1", "R1_10_1", "RC1_10_1",
]
MDRP_REQUIRED_FILES = ("couriers.txt", "orders.txt", "restaurants.txt", "instance_characteristics.txt")
MDRP_SMOKE = ("mdrp-smoke-low", "mdrp-smoke-medium", "mdrp-smoke-high")
MDRP_CORE = (*MDRP_SMOKE, *(f"mdrp-core-{index}" for index in range(4, 11)))
ICAPS_SMOKE = ("icaps-case-1", "icaps-case-2")
ICAPS_CORE = tuple(f"icaps-case-{index}" for index in range(1, 6))
DPDP_STRESS_SMOKE = ("low",)
DPDP_STRESS_CORE = ("low", "medium", "high", "burst", "driver-scarcity", "bad-geo", "provider-timeout")
HCM_SCENARIOS = ("normal-clear", "heavy-rain", "traffic-shock", "route-ambiguity", "driver-scarcity", "dinner-peak-high-density")
HCM_MODES = ("full-system", "no-llm", "no-heavy-ml", "ortools-baseline")
HCM_SIZES_BY_LEVEL = {"smoke": ("S",), "core": ("S", "M"), "full": ("S", "M", "L")}


@dataclass(frozen=True)
class CheckRow:
    group: str
    item: str
    status: str
    path: str = ""
    reason: str = ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def row(group: str, item: str, path: Path, required: bool = True) -> CheckRow:
    if path.exists():
        return CheckRow(group, item, "PASS", str(path))
    return CheckRow(group, item, "MISSING_REQUIRED" if required else "MISSING_OPTIONAL", str(path), "file-or-artifact-missing")


def academic_instances(level: str) -> dict[str, Sequence[str]]:
    return ACADEMIC_SMOKE if level == "smoke" else ACADEMIC_CORE


def homberger_instances(level: str) -> Sequence[str]:
    return HOMBERGER_SMOKE if level == "smoke" else HOMBERGER_CORE


def mdrp_instances(level: str) -> Sequence[str]:
    return MDRP_SMOKE if level == "smoke" else MDRP_CORE


def icaps_instances(level: str) -> Sequence[str]:
    return ICAPS_SMOKE if level == "smoke" else ICAPS_CORE


def hcm_cells(level: str) -> Iterable[tuple[str, str, str]]:
    scenarios = ("normal-clear",) if level == "smoke" else HCM_SCENARIOS
    modes = ("full-system",) if level == "smoke" else HCM_MODES
    for scenario in scenarios:
        for size in HCM_SIZES_BY_LEVEL[level]:
            for mode in modes:
                yield scenario, size, mode


def check_academic(root: Path, level: str) -> list[CheckRow]:
    rows: list[CheckRow] = []
    for family, instances in academic_instances(level).items():
        for instance in instances:
            rows.append(row("academic", f"{family}/{instance}", root / family / f"{instance}.txt"))
    for instance in homberger_instances(level):
        rows.append(row("homberger", instance, root / "homberger" / f"{instance}.txt"))
    return rows


def check_mdrp(root: Path, level: str) -> list[CheckRow]:
    rows: list[CheckRow] = []
    for instance in mdrp_instances(level):
        for filename in MDRP_REQUIRED_FILES:
            rows.append(row("mdrplib", f"{instance}/{filename}", root / "mdrplib" / instance / filename))
    return rows


def check_icaps(root: Path, level: str) -> list[CheckRow]:
    rows = [row("icaps", "factory_info.csv", root / "icaps-dpdp" / "factory_info.csv")]
    for instance in icaps_instances(level):
        suffix = instance.rsplit("-", 1)[-1]
        rows.append(row("icaps", f"{instance}/50_{suffix}.csv", root / "icaps-dpdp" / instance / f"50_{suffix}.csv"))
        rows.append(row("icaps", f"{instance}/vehicle_info_5.csv", root / "icaps-dpdp" / instance / "vehicle_info_5.csv"))
    return rows


def check_hcm(full_system_root: Path, level: str, require_hcm: bool) -> list[CheckRow]:
    rows: list[CheckRow] = []
    for scenario, size, mode in hcm_cells(level):
        pattern = f"mode-comparison/{mode}/{scenario}/{size}/dispatch-quality*.json"
        matches = sorted(full_system_root.glob(pattern))
        status = "PASS" if matches else ("MISSING_REQUIRED" if require_hcm else "MISSING_OPTIONAL")
        rows.append(CheckRow("hcm", f"{scenario}/{size}/{mode}", status, str(matches[-1] if matches else full_system_root / pattern), "artifact-missing" if not matches else ""))
    return rows


def build_readiness(level: str, benchmark_root: Path, full_system_root: Path, require_hcm: bool) -> dict[str, Any]:
    rows = [
        *check_academic(benchmark_root, level),
        *check_mdrp(benchmark_root, level),
        *check_icaps(benchmark_root, level),
        *check_hcm(full_system_root, level, require_hcm),
    ]
    counts = {status: sum(1 for item in rows if item.status == status) for status in ("PASS", "MISSING_REQUIRED", "MISSING_OPTIONAL")}
    ready = counts["MISSING_REQUIRED"] == 0
    return {
        "schemaVersion": "certification-dataset-readiness/v1",
        "level": level,
        "datasetReady": ready,
        "counts": counts,
        "rows": [item.__dict__ for item in rows],
        "blockers": [item.__dict__ for item in rows if item.status == "MISSING_REQUIRED"],
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Certification Dataset Readiness",
        "",
        f"- level: `{payload['level']}`",
        f"- DATASET_READY = `{str(payload['datasetReady']).lower()}`",
        f"- counts: `{payload['counts']}`",
        "",
        "| Group | Item | Status | Reason | Path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload["rows"]:
        lines.append(f"| `{item['group']}` | `{item['item']}` | `{item['status']}` | `{item.get('reason', '')}` | `{item['path']}` |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify certification datasets before running large benchmark suites.")
    parser.add_argument("--level", choices=("smoke", "core", "full"), default="core")
    parser.add_argument("--benchmark-root", default=str(DEFAULT_BENCHMARK_ROOT))
    parser.add_argument("--full-system-root", default=str(DEFAULT_FULL_SYSTEM_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--require-hcm", action="store_true", help="Treat missing HCM mode-comparison artifacts as blockers.")
    args = parser.parse_args(argv)
    payload = build_readiness(args.level, Path(args.benchmark_root), Path(args.full_system_root), args.require_hcm)
    output_root = Path(args.output_root)
    write_json(output_root / "dataset_readiness.json", payload)
    (output_root / "dataset_readiness.md").write_text(markdown(payload), encoding="utf-8")
    print(f"[DATASET READINESS] ready={payload['datasetReady']} level={args.level} blockers={len(payload['blockers'])}")
    print(output_root / "dataset_readiness.json")
    return 0 if payload["datasetReady"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
