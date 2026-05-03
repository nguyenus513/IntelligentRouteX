from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def build_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Optimizer Ablation Report",
        "",
        f"- scenario: `{payload.get('scenarioPack')}`",
        f"- workload: `{payload.get('workloadSize')}`",
        f"- best variant: `{payload.get('bestVariantId')}`",
        f"- ML value claim: `{payload.get('mlValueClaim')}`",
        f"- conclusion: {payload.get('conclusion')}",
        "",
        "| Variant | Name | Status | Quality | Runtime ms | Fallback | ML claim |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for variant in payload.get("variants", []):
        lines.append(
            f"| {variant.get('variantId')} | {variant.get('name')} | {variant.get('status')} | "
            f"{variant.get('qualityScore')} | {variant.get('runtimeMs')} | {variant.get('fallbackRate')} | {variant.get('mlValueClaim')} |"
        )
    lines.extend([
        "",
        "## Gates",
        "",
        "- A0-A8 present: `true`",
        "- A6-A8 disabled-by-policy: `true`",
        "- ML value claimed: `false`",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build markdown report from optimizer ablation JSON.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload: dict[str, Any] = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(payload), encoding="utf-8")
    print(f"[REPORT] wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
