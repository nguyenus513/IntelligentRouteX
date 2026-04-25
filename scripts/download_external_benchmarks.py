from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Dict

SOURCES: Dict[str, Dict[str, str]] = {
    "solomon/C101.txt": {
        "primary": "https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip",
        "mirror": "https://raw.githubusercontent.com/iRB-Lab/py-ga-VRPTW/master/data/text/C101.txt",
    },
    "solomon/R101.txt": {
        "primary": "https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip",
        "mirror": "https://raw.githubusercontent.com/iRB-Lab/py-ga-VRPTW/master/data/text/R101.txt",
    },
    "solomon/RC101.txt": {
        "primary": "https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip",
        "mirror": "https://raw.githubusercontent.com/iRB-Lab/py-ga-VRPTW/master/data/text/RC101.txt",
    },
    "li-lim-pdptw/LC101.txt": {
        "primary": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_100.zip",
        "mirror": "https://git.xkool.org/hw/or-tools/-/raw/b40d6b59e3bf7fc2c2c103a543a556eff8b75626/examples/data/pdptw/lc101.txt",
    },
    "li-lim-pdptw/LR101.txt": {
        "primary": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_100.zip",
        "mirror": "https://git.xkool.org/hw/or-tools/-/raw/b40d6b59e3bf7fc2c2c103a543a556eff8b75626/examples/data/pdptw/lr101.txt",
    },
    "li-lim-pdptw/LRC101.txt": {
        "primary": "https://www.sintef.no/contentassets/1338af68996841d3922bc8e87adc430c/pdp_100.zip",
        "mirror": "https://git.xkool.org/hw/or-tools/-/raw/b40d6b59e3bf7fc2c2c103a543a556eff8b75626/examples/data/pdptw/lrc101.txt",
    },
}


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "IntelligentRouteX external benchmark fetcher"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    return payload.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download external benchmark smoke instances into the official-data area.")
    parser.add_argument("--output-root", default="benchmarks/external")
    parser.add_argument("--allow-mirror", action="store_true", help="Use vetted raw mirrors when primary SINTEF assets are blocked.")
    args = parser.parse_args()
    root = Path(args.output_root)
    for child in ("solomon", "li-lim-pdptw", "cvrplib", "vrp-rep"):
        (root / child).mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": "external-benchmark-download-manifest/v1",
        "status": "downloaded",
        "entries": [],
        "notes": [
            "Primary SINTEF zip URLs can be protected by browser challenges in headless environments.",
            "Mirror downloads are raw text copies used only when --allow-mirror is explicit.",
        ],
    }
    failures = 0
    for relative_path, sources in SOURCES.items():
        target = root / "official" / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        source_used = None
        error = None
        for kind in ("primary", "mirror"):
            if kind == "mirror" and not args.allow_mirror:
                continue
            try:
                text = fetch_text(sources[kind])
                if "Enable JavaScript and cookies" in text:
                    raise RuntimeError("browser challenge returned instead of benchmark data")
                target.write_text("\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip() + "\n", encoding="utf-8")
                source_used = kind
                break
            except Exception as exception:
                error = str(exception)
        if source_used is None:
            failures += 1
        manifest["entries"].append({
            "path": str(target),
            "primary": sources["primary"],
            "mirror": sources["mirror"],
            "sourceUsed": source_used,
            "error": error if source_used is None else None,
        })
    manifest["status"] = "failed" if failures else "downloaded"
    manifest_path = root / "official" / "download_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(manifest_path)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
