from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

from run_phase55_promotion_guard import write_json


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "benchmark" / "phase84_unified_optimizer_v1" / "antihardcode_report.json"
FORBIDDEN = [
    r"startswith\([\"']LRC",
    r"startswith\([\"']LC1",
    r"instanceName\s*==",
    r"benchmarkFamily\s*==",
    r"suiteName\s*==",
    r"vroom.*route",
    r"bks.*route",
    r"reference.*route",
]


def scan(root: Path = REPO_ROOT / "scripts" / "optimizer") -> Dict[str, Any]:
    violations: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if re.search(pattern, text, flags=re.IGNORECASE):
                violations.append({"path": str(path), "pattern": pattern})
    return {"schemaVersion": "phase84-antihardcode-guard/v1", "gate": "PASS" if not violations else "FAIL", "violations": violations}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 84 anti-hardcode guard.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = scan()
    write_json(Path(args.output), report)
    print(f"[PHASE84 ANTIHARDCODE] {report['gate']} wrote {args.output}")
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
