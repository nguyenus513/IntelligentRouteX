from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def inspect_capability() -> dict[str, Any]:
    available = importlib.util.find_spec("pyvrp") is not None
    payload: dict[str, Any] = {
        "schemaVersion": "pyvrp-capability/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "package": "pyvrp",
        "available": available,
        "status": "AVAILABLE" if available else "SKIPPED",
        "version": None,
        "features": {},
        "reasons": [] if available else ["pyvrp-package-not-installed"],
    }
    if not available:
        return payload
    try:
        payload["version"] = importlib.metadata.version("pyvrp")
    except importlib.metadata.PackageNotFoundError:
        payload["version"] = "unknown"
    try:
        import pyvrp  # type: ignore
        from pyvrp import Model  # type: ignore
        payload["features"] = {
            "Model": Model is not None,
            "solve": hasattr(pyvrp, "solve"),
            "stopCriterion": importlib.util.find_spec("pyvrp.stop") is not None,
        }
    except Exception as exception:
        payload["status"] = "ERROR"
        payload["reasons"].append(f"pyvrp-import-error: {type(exception).__name__}: {exception}")
    return payload


def markdown(payload: dict[str, Any]) -> str:
    return "\n".join([
        "# PyVRP Capability",
        "",
        f"- status: `{payload['status']}`",
        f"- available: `{payload['available']}`",
        f"- version: `{payload.get('version')}`",
        f"- features: `{payload.get('features', {})}`",
        f"- reasons: `{payload.get('reasons', [])}`",
        "",
    ])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect PyVRP/HGS capability for Phase 13.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = inspect_capability()
    (output_dir / "pyvrp_capability.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "pyvrp_capability.md").write_text(markdown(payload), encoding="utf-8")
    print(f"[PYVRP CAPABILITY] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
