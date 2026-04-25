from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare external benchmark directories. Network download is intentionally explicit in later versions.")
    parser.add_argument("--output-root", default="benchmarks/external")
    args = parser.parse_args()
    root = Path(args.output_root)
    for child in ("solomon", "li-lim-pdptw", "cvrplib", "vrp-rep"):
        (root / child).mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": "external-benchmark-download-manifest/v1",
        "status": "fixtures-ready",
        "note": "Official downloads are not performed automatically; add source URLs/checksums before enabling network fetch.",
    }
    (root / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(root / "download_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
