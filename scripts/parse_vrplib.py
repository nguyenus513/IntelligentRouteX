from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse VRPLIB/CVRPLIB instances. Placeholder until CVRPLIB suite is enabled.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "schemaVersion": "external-benchmark-normalized/v1",
        "verdict": "EVIDENCE_GAP",
        "reason": "vrplib-parser-not-enabled",
        "input": args.input,
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
