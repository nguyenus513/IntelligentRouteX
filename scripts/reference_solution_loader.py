from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REFERENCE_DIRS = (
    Path("benchmarks/external/official/solomon/solutions"),
    Path("benchmarks/external/solomon/solutions"),
    Path("benchmarks/external/reference"),
    Path("artifacts/benchmark/reference-solutions"),
)


def parse_reference_text(text: str, depot: str = "0") -> list[list[str]]:
    routes: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            stripped = stripped.split(":", 1)[1]
        stops = re.findall(r"\d+", stripped)
        if not stops:
            continue
        if stops[0] != depot:
            stops = [depot] + stops
        if stops[-1] != depot:
            stops = stops + [depot]
        if len(stops) > 2:
            routes.append(stops)
    return routes


def load_reference_solution(path: Path, depot: str = "0") -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        routes = [[str(stop) for stop in route] for route in payload.get("routes", [])]
    else:
        routes = parse_reference_text(text, depot)
        payload = {"instance": path.stem}
    return {"schemaVersion": "external-benchmark-solution/v1", "solver": f"reference:{path.name}", "routes": routes, "referencePath": str(path), "referenceInstance": payload.get("instance")}


def find_reference_solution(instance_name: str, repo_root: Path, depot: str = "0") -> dict[str, Any] | None:
    names = [instance_name, instance_name.upper(), instance_name.lower()]
    suffixes = [".json", ".txt", ".sol"]
    for directory in REFERENCE_DIRS:
        root = repo_root / directory
        for name in names:
            for suffix in suffixes:
                path = root / f"{name}{suffix}"
                if path.exists():
                    return load_reference_solution(path, depot)
    return None
