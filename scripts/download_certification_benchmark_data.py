from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official"

MDRPLIB_REPO = "https://raw.githubusercontent.com/grubhub/mdrplib/master/public_instances"
ICAPS_REPO = "https://raw.githubusercontent.com/huawei-noah/xingtian/master/simulator/dpdp_competition/benchmark"

MDRPLIB_SMOKE_INSTANCES = {
    "mdrp-smoke-low": "0o100t100s1p100",
    "mdrp-smoke-medium": "5r50t75s1p100",
    "mdrp-smoke-high": "9r50t75s2p125",
}
MDRPLIB_REQUIRED_FILES = ("couriers.txt", "orders.txt", "restaurants.txt", "instance_characteristics.txt")

ICAPS_SMOKE_INSTANCES = {
    "icaps-case-1": ("instance_1", "50_1.csv", "vehicle_info_5.csv"),
    "icaps-case-2": ("instance_2", "50_2.csv", "vehicle_info_5.csv"),
}
ICAPS_CORE_INSTANCES = {
    **ICAPS_SMOKE_INSTANCES,
    "icaps-case-3": ("instance_3", "50_3.csv", "vehicle_info_5.csv"),
    "icaps-case-4": ("instance_4", "50_4.csv", "vehicle_info_5.csv"),
    "icaps-case-5": ("instance_5", "50_5.csv", "vehicle_info_5.csv"),
}

HOMBERGER_DOWNLOAD_NOTES = {
    "source": "SINTEF Gehring & Homberger VRPTW benchmark pages",
    "reason": "Direct automated download is often blocked by Cloudflare/browser challenge. Place official .txt files under benchmarks/external/official/homberger/.",
    "expectedSmokeFiles": ["C1_2_1.txt", "R1_2_1.txt", "RC1_2_1.txt"],
    "expectedCoreFiles": [
        "C1_2_1.txt", "R1_2_1.txt", "RC1_2_1.txt",
        "C1_4_1.txt", "R1_4_1.txt", "RC1_4_1.txt",
        "C1_6_1.txt", "R1_6_1.txt", "RC1_6_1.txt",
        "C1_8_1.txt", "R1_8_1.txt", "RC1_8_1.txt",
        "C1_10_1.txt", "R1_10_1.txt", "RC1_10_1.txt",
    ],
}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_entry(path: Path, url: str | None = None) -> dict[str, Any]:
    payload = path.read_bytes()
    entry = {"path": str(path), "bytes": len(payload), "sha256": sha256_bytes(payload)}
    if url:
        entry["url"] = url
    return entry


def download_text(url: str, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    path.write_bytes(payload)
    return {"url": url, "path": str(path), "bytes": len(payload), "sha256": sha256_bytes(payload)}


def download_mdrplib(root: Path, instances: Iterable[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for local_name in instances:
        source_name = MDRPLIB_SMOKE_INSTANCES[local_name]
        for filename in MDRPLIB_REQUIRED_FILES:
            url = f"{MDRPLIB_REPO}/{source_name}/{filename}"
            target = root / "mdrplib" / local_name / filename
            entry = download_text(url, target)
            entry.update({"benchmark": "mdrplib", "instance": local_name, "sourceInstance": source_name})
            entries.append(entry)
    return entries


def download_icaps(root: Path, instances: dict[str, tuple[str, str, str]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    factory_target = root / "icaps-dpdp" / "factory_info.csv"
    entries.append({"benchmark": "icaps-dpdp", **download_text(f"{ICAPS_REPO}/factory_info.csv", factory_target)})
    for local_name, (folder, orders_file, vehicle_file) in instances.items():
        for filename in (orders_file, vehicle_file):
            url = f"{ICAPS_REPO}/{folder}/{filename}"
            target = root / "icaps-dpdp" / local_name / filename
            entry = download_text(url, target)
            entry.update({"benchmark": "icaps-dpdp", "instance": local_name, "sourceInstance": folder})
            entries.append(entry)
    return entries


def write_homberger_manifest(root: Path) -> dict[str, Any]:
    homberger_root = root / "homberger"
    homberger_root.mkdir(parents=True, exist_ok=True)
    manifest_path = homberger_root / "README.download.json"
    write_json(manifest_path, HOMBERGER_DOWNLOAD_NOTES)
    missing_path = homberger_root / "missing_official_files.json"
    expected = HOMBERGER_DOWNLOAD_NOTES["expectedCoreFiles"]
    missing = [filename for filename in expected if not (homberger_root / filename).exists()]
    present = [file_entry(homberger_root / filename) for filename in expected if (homberger_root / filename).exists()]
    write_json(missing_path, {
        "schemaVersion": "homberger-official-data-gap/v1",
        "policy": "official-only",
        "missingFiles": missing,
        "presentFiles": present,
        "verdict": "PASS" if not missing else "EVIDENCE_GAP",
    })
    return {
        "benchmark": "homberger-vrptw",
        "path": str(manifest_path),
        "missingPath": str(missing_path),
        "policy": "official-only",
        "missingCount": len(missing),
        **HOMBERGER_DOWNLOAD_NOTES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download public/official benchmark data used by the certification suite.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--groups", default="mdrplib,icaps,homberger", help="Comma-separated: mdrplib,icaps,homberger")
    parser.add_argument("--level", choices=("smoke", "core"), default="smoke")
    args = parser.parse_args()

    root = Path(args.output_root)
    groups = {part.strip().lower() for part in args.groups.split(",") if part.strip()}
    manifest: dict[str, Any] = {
        "schemaVersion": "certification-benchmark-download-manifest/v2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "level": args.level,
        "entries": [],
    }
    if "mdrplib" in groups:
        manifest["entries"].extend(download_mdrplib(root, MDRPLIB_SMOKE_INSTANCES.keys()))
    if "icaps" in groups:
        manifest["entries"].extend(download_icaps(root, ICAPS_SMOKE_INSTANCES if args.level == "smoke" else ICAPS_CORE_INSTANCES))
    if "homberger" in groups:
        manifest["entries"].append(write_homberger_manifest(root))
    write_json(root / "download_manifest.json", manifest)
    print(root / "download_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
