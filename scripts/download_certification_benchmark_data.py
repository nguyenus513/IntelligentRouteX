from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "benchmarks" / "external" / "official"

MDRPLIB_REPO = "https://raw.githubusercontent.com/grubhub/mdrplib/master/public_instances"
ICAPS_REPO = "https://raw.githubusercontent.com/huawei-noah/xingtian/master/simulator/dpdp_competition/benchmark"
SOLOMON_ZIP_URL = "https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip"
LI_LIM_ZIP_URLS = {
    "100": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_100.zip",
    "200": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_200.zip",
    "400": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_400.zip",
    "600": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_600.zip",
    "800": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_800.zip",
    "1000": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_1000.zip",
}

MDRPLIB_SMOKE_INSTANCES = {
    "mdrp-smoke-low": "0o100t100s1p100",
    "mdrp-smoke-medium": "5r50t75s1p100",
    "mdrp-smoke-high": "9r50t75s2p125",
}
MDRPLIB_CORE_INSTANCES = {
    **MDRPLIB_SMOKE_INSTANCES,
    "mdrp-core-4": "1o50t75s1p100",
    "mdrp-core-5": "2o50t100s1p100",
    "mdrp-core-6": "3r50t75s2p100",
    "mdrp-core-7": "4o100t75s1p125",
    "mdrp-core-8": "5r50t75s1p100",
    "mdrp-core-9": "6o100t100s2p125",
    "mdrp-core-10": "7r50t100s2p125",
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
    "reason": "Official SINTEF zip files are downloaded when available. If the site blocks automated access, place official .txt files under benchmarks/external/official/homberger/.",
    "expectedSmokeFiles": ["C1_2_1.txt", "R1_2_1.txt", "RC1_2_1.txt"],
    "expectedCoreFiles": [
        "C1_2_1.txt", "R1_2_1.txt", "RC1_2_1.txt",
        "C1_4_1.txt", "R1_4_1.txt", "RC1_4_1.txt",
        "C1_6_1.txt", "R1_6_1.txt", "RC1_6_1.txt",
        "C1_8_1.txt", "R1_8_1.txt", "RC1_8_1.txt",
        "C1_10_1.txt", "R1_10_1.txt", "RC1_10_1.txt",
    ],
}

HOMBERGER_ZIP_URLS = {
    "200": "https://www.sintef.no/globalassets/project/top/vrptw/homberger/200/homberger_200_customer_instances.zip",
    "400": "https://www.sintef.no/globalassets/project/top/vrptw/homberger/400/homberger_400_customer_instances.zip",
    "600": "https://www.sintef.no/globalassets/project/top/vrptw/homberger/600/homberger_600_customer_instances.zip",
    "800": "https://www.sintef.no/globalassets/project/top/vrptw/homberger/800/homberger_800_customer_instances.zip",
    "1000": "https://www.sintef.no/globalassets/project/top/vrptw/homberger/1000/homberger_1000_customer_instances.zip",
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


def download_binary(url: str, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "IntelligentRouteX certification downloader"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    path.write_bytes(payload)
    return {"url": url, "path": str(path), "bytes": len(payload), "sha256": sha256_bytes(payload)}


def download_mdrplib(root: Path, instances: Iterable[str], *, level: str) -> list[dict[str, Any]]:
    source_map = MDRPLIB_SMOKE_INSTANCES if level == "smoke" else MDRPLIB_CORE_INSTANCES
    entries: list[dict[str, Any]] = []
    for local_name in instances:
        source_name = source_map[local_name]
        for filename in MDRPLIB_REQUIRED_FILES:
            url = f"{MDRPLIB_REPO}/{source_name}/{filename}"
            target = root / "mdrplib" / local_name / filename
            entry = download_text(url, target)
            entry.update({"benchmark": "mdrplib", "instance": local_name, "sourceInstance": source_name})
            entries.append(entry)
    return entries


def extract_selected_zip_members(url: str, archive_path: Path, output_dir: Path, selected_names: set[str] | None = None) -> dict[str, Any]:
    archive = download_binary(url, archive_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive_path) as zip_file:
        for member in zip_file.namelist():
            filename = Path(member).name
            if not filename or not filename.lower().endswith(".txt"):
                continue
            if selected_names is not None and filename.upper() not in selected_names:
                continue
            target = output_dir / filename.upper().replace(".TXT", ".txt")
            target.write_bytes(zip_file.read(member))
            extracted.append(file_entry(target, url))
    return {"archive": archive, "extractedFiles": extracted, "extractedCount": len(extracted)}


def download_solomon(root: Path) -> dict[str, Any]:
    selected = {"C101.TXT", "C201.TXT", "R101.TXT", "R201.TXT", "RC101.TXT", "RC201.TXT"}
    return {"benchmark": "solomon-vrptw", **extract_selected_zip_members(
        SOLOMON_ZIP_URL,
        root / "archives" / "solomon-100.zip",
        root / "solomon",
        selected,
    )}


def download_li_lim(root: Path, level: str) -> dict[str, Any]:
    required_core = {"LC101.TXT", "LC201.TXT", "LR101.TXT", "LR201.TXT", "LRC101.TXT", "LRC201.TXT"}
    sizes = ("100",) if level == "smoke" else tuple(LI_LIM_ZIP_URLS.keys())
    extracted: list[dict[str, Any]] = []
    archives: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    output_dir = root / "li-lim-pdptw"
    output_dir.mkdir(parents=True, exist_ok=True)
    for size in sizes:
        url = LI_LIM_ZIP_URLS[size]
        archive_path = root / "archives" / f"pdp_{size}.zip"
        try:
            archive = download_binary(url, archive_path)
            archives.append(archive)
            with zipfile.ZipFile(archive_path) as zip_file:
                for member in zip_file.namelist():
                    filename = Path(member).name
                    if not filename or not filename.lower().endswith(".txt"):
                        continue
                    if level == "smoke" and filename.upper() not in required_core:
                        continue
                    target = output_dir / filename.upper().replace(".TXT", ".txt")
                    target.write_bytes(zip_file.read(member))
                    extracted.append(file_entry(target, url))
        except Exception as exc:
            failures.append({"size": size, "url": url, "error": str(exc)})
    return {"benchmark": "li-lim-pdptw", "archives": archives, "extractedFiles": extracted, "extractedCount": len(extracted), "downloadFailures": failures}


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


def download_homberger(root: Path, level: str) -> dict[str, Any]:
    homberger_root = root / "homberger"
    archive_root = homberger_root / "archives"
    homberger_root.mkdir(parents=True, exist_ok=True)
    expected = HOMBERGER_DOWNLOAD_NOTES["expectedSmokeFiles"] if level == "smoke" else HOMBERGER_DOWNLOAD_NOTES["expectedCoreFiles"]
    expected_by_upper = {filename.upper(): filename for filename in expected}
    required_sizes = ["200"] if level == "smoke" else ["200", "400", "600", "800", "1000"]
    archives: list[dict[str, Any]] = []
    extracted: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for size in required_sizes:
        url = HOMBERGER_ZIP_URLS[size]
        archive_path = archive_root / Path(url).name
        try:
            archives.append({"benchmark": "homberger-vrptw", "size": size, **download_binary(url, archive_path)})
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.namelist():
                    if not member.lower().endswith(".txt"):
                        continue
                    member_name = Path(member).name.upper()
                    if member_name not in expected_by_upper:
                        continue
                    target_name = expected_by_upper[member_name]
                    target_path = homberger_root / target_name
                    target_path.write_bytes(archive.read(member))
                    extracted.append({"benchmark": "homberger-vrptw", "size": size, "archiveMember": member, **file_entry(target_path, url)})
        except Exception as exception:
            failures.append({"benchmark": "homberger-vrptw", "size": size, "url": url, "error": str(exception)})
    manifest = write_homberger_manifest(root)
    manifest["archives"] = archives
    manifest["extractedFiles"] = extracted
    manifest["downloadFailures"] = failures
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Download public/official benchmark data used by the certification suite.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--groups", default="solomon,li-lim,mdrplib,icaps,homberger", help="Comma-separated: solomon,li-lim,mdrplib,icaps,homberger")
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
    if "solomon" in groups:
        manifest["entries"].append(download_solomon(root))
    if "li-lim" in groups:
        manifest["entries"].append(download_li_lim(root, args.level))
    if "mdrplib" in groups:
        manifest["entries"].extend(download_mdrplib(root, MDRPLIB_SMOKE_INSTANCES.keys() if args.level == "smoke" else MDRPLIB_CORE_INSTANCES.keys(), level=args.level))
    if "icaps" in groups:
        manifest["entries"].extend(download_icaps(root, ICAPS_SMOKE_INSTANCES if args.level == "smoke" else ICAPS_CORE_INSTANCES))
    if "homberger" in groups:
        manifest["entries"].append(download_homberger(root, args.level))
    write_json(root / "download_manifest.json", manifest)
    print(root / "download_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
