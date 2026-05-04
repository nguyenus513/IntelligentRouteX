from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from run_external_benchmark_certification import parse_instance, resolve_instance_path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SYNTHETIC_DIR = REPO_ROOT / "benchmarks" / "synthetic_food" / "generated_v1"


def load_normalized_json(path: Path) -> Dict[str, Any]:
    instance = json.loads(path.read_text(encoding="utf-8"))
    if instance.get("schemaVersion") != "external-benchmark-normalized/v1":
        raise ValueError(f"Unsupported normalized instance schema: {path}")
    if instance.get("problemType") != "PDPTW":
        raise ValueError(f"Unsupported normalized instance problem type: {path}")
    return instance


def resolve_synthetic_path(instance_name: str, synthetic_dir: Path = DEFAULT_SYNTHETIC_DIR) -> Path:
    path = synthetic_dir / f"{instance_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Synthetic food instance not found: {path}")
    return path


def load_benchmark_instance(source: str, instance_name: str, data_source: str = "auto", synthetic_dir: Path = DEFAULT_SYNTHETIC_DIR) -> Dict[str, Any]:
    normalized_source = source.lower().replace("_", "-")
    if normalized_source in {"synthetic-food", "synthetic_food"}:
        return load_normalized_json(resolve_synthetic_path(instance_name, synthetic_dir))
    return parse_instance("li-lim", resolve_instance_path("li-lim", instance_name, data_source))
