from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from run_external_benchmark_certification import parse_instance, resolve_instance_path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SYNTHETIC_DIR = REPO_ROOT / "benchmarks" / "synthetic_food" / "generated_v1"
DEFAULT_VROOM_CAPABILITY_DIR = REPO_ROOT / "benchmarks" / "vroom_capability" / "generated_v1"
DEFAULT_LIVE_SNAPSHOT_DIR = REPO_ROOT / "benchmarks" / "live_snapshots" / "converted_v1"
DEFAULT_PHASE90_OPPORTUNITY_DIR = REPO_ROOT / "benchmarks" / "phase90_opportunity" / "generated_v1"


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


def resolve_vroom_capability_path(instance_name: str, capability_dir: Path = DEFAULT_VROOM_CAPABILITY_DIR) -> Path:
    path = capability_dir / f"{instance_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"VROOM capability instance not found: {path}")
    return path


def resolve_phase90_opportunity_path(instance_name: str, opportunity_dir: Path = DEFAULT_PHASE90_OPPORTUNITY_DIR) -> Path:
    path = opportunity_dir / f"{instance_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Phase 90 opportunity instance not found: {path}")
    return path


def resolve_live_snapshot_path(instance_name: str, live_snapshot_dir: Path | None = None) -> Path:
    root = live_snapshot_dir or DEFAULT_LIVE_SNAPSHOT_DIR
    path = root / f"{instance_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Converted live snapshot instance not found: {path}")
    return path


def load_benchmark_instance(source: str, instance_name: str, data_source: str = "auto", synthetic_dir: Path = DEFAULT_SYNTHETIC_DIR) -> Dict[str, Any]:
    normalized_source = source.lower().replace("_", "-")
    if normalized_source in {"synthetic-food", "synthetic_food"}:
        return load_normalized_json(resolve_synthetic_path(instance_name, synthetic_dir))
    if normalized_source in {"vroom-capability", "vroom_capability"}:
        return load_normalized_json(resolve_vroom_capability_path(instance_name))
    if normalized_source in {"live-snapshot", "live_snapshot"}:
        return load_normalized_json(resolve_live_snapshot_path(instance_name))
    if normalized_source in {"phase90-opportunity", "phase90_opportunity"}:
        return load_normalized_json(resolve_phase90_opportunity_path(instance_name))
    return parse_instance("li-lim", resolve_instance_path("li-lim", instance_name, data_source))
