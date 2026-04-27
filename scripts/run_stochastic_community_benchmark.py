from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "benchmarks" / "external" / "official" / "stochastic"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "stochastic-community"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def build_result(data_root: Path) -> Dict[str, Any]:
    manifest_path = data_root / "manifest.json"
    if not manifest_path.exists():
        return {
            "schemaVersion": "stochastic-community/v1",
            "benchmarkFamily": "public-stochastic-vrp",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["stochastic-data-manifest-missing"],
            "instanceFileCount": 0,
        }
    manifest = read_json(manifest_path)
    instance_count = int(manifest.get("instanceFileCount", 0))
    if instance_count == 0:
        return {
            "schemaVersion": "stochastic-community/v1",
            "benchmarkFamily": "public-stochastic-vrp",
            "sourceManifest": str(manifest_path),
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": manifest.get("verdictReasons", ["public-stochastic-vrp-data-missing"]),
            "instanceFileCount": 0,
            "parserIntegrated": False,
            "checkerIntegrated": False,
        }
    return {
        "schemaVersion": "stochastic-community/v1",
        "benchmarkFamily": "public-stochastic-vrp",
        "sourceManifest": str(manifest_path),
        "finalVerdict": "PASS_WITH_LIMITS",
        "verdictReasons": ["stochastic-parser-checker-not-yet-integrated"],
        "instanceFileCount": instance_count,
        "parserIntegrated": False,
        "checkerIntegrated": False,
    }


def markdown(result: Dict[str, Any]) -> str:
    lines = [
        "# Stochastic Community Benchmark",
        "",
        f"FINAL_VERDICT = {result['finalVerdict']}",
        "",
        f"- instance files: `{result.get('instanceFileCount', 0)}`",
        f"- parser integrated: `{result.get('parserIntegrated', False)}`",
        f"- checker integrated: `{result.get('checkerIntegrated', False)}`",
        f"- reasons: `{', '.join(result.get('verdictReasons', []))}`",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run public stochastic VRP community evidence rail.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    result = build_result(Path(args.data_root))
    write_json(output_root / "stochastic_results.json", result)
    (output_root / "stochastic_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[STOCHASTIC JSON] {output_root / 'stochastic_results.json'}")
    print(f"[STOCHASTIC REPORT] {output_root / 'stochastic_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
