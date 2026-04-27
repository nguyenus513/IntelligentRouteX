from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "ml-intelligence-community"


def package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_benchmark() -> Dict[str, Any]:
    rl4co_available = package_available("rl4co")
    torch_available = package_available("torch")
    if not rl4co_available:
        return {
            "schemaVersion": "ml-intelligence-community/v1",
            "benchmarkFamily": "rl4co",
            "finalVerdict": "EVIDENCE_GAP",
            "verdictReasons": ["rl4co-package-not-installed", "our-ml-policy-adapter-missing"],
            "rl4coAvailable": False,
            "torchAvailable": torch_available,
            "mlValueProven": False,
        }
    return {
        "schemaVersion": "ml-intelligence-community/v1",
        "benchmarkFamily": "rl4co",
        "finalVerdict": "PASS_WITH_LIMITS",
        "verdictReasons": ["rl4co-installed-but-policy-adapter-pending"],
        "rl4coAvailable": True,
        "torchAvailable": torch_available,
        "mlValueProven": False,
    }


def markdown(result: Dict[str, Any]) -> str:
    return "\n".join([
        "# ML Intelligence Community Benchmark",
        "",
        f"FINAL_VERDICT = {result['finalVerdict']}",
        "",
        f"- benchmark family: `{result['benchmarkFamily']}`",
        f"- RL4CO available: `{result['rl4coAvailable']}`",
        f"- torch available: `{result['torchAvailable']}`",
        f"- ML value proven: `{result['mlValueProven']}`",
        f"- reasons: `{', '.join(result.get('verdictReasons', []))}`",
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run community ML intelligence benchmark evidence rail.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    output_root = Path(args.output_root)
    result = run_benchmark()
    write_json(output_root / "ml_intelligence_results.json", result)
    (output_root / "ml_intelligence_report.md").write_text(markdown(result), encoding="utf-8")
    print(f"[ML INTELLIGENCE JSON] {output_root / 'ml_intelligence_results.json'}")
    print(f"[ML INTELLIGENCE REPORT] {output_root / 'ml_intelligence_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
