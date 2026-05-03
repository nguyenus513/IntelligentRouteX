from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "full-adaptive"
TARGET_CASES = (
    ("normal-clear", "S"),
    ("heavy-rain", "S"),
    ("traffic-shock", "S"),
    ("forecast-heavy", "S"),
)
TARGET_STAGE_CHOICES = ("bundle-pool", "route-proposal-pool", "scenario-evaluation")
ROUTE_GENERATION_FOCUS_CASES = (("heavy-rain", "S"), ("traffic-shock", "S"))
VERDICTS = ("PASS", "PASS_WITH_LIMITS", "REGRESSION_RISK", "EVIDENCE_GAP")


@dataclass(frozen=True)
class ValidationCell:
    scenario_pack: str
    size: str
    baseline: str
    decision_mode: str
    prompt_family: str
    execution_mode: str
    profile: str
    root_type: str

    @property
    def case_id(self) -> str:
        return f"{self.scenario_pack}/{self.size}/{self.execution_mode}/{self.decision_mode}/{self.prompt_family}"


@dataclass(frozen=True)
class AdaptiveTraceRow:
    root_type: str
    root_path: str
    scenario_pack: str
    size: str
    execution_mode: str
    decision_mode: str
    prompt_family: str
    baseline: str
    trace_id: str
    stage_name: str
    worker_name: str
    decision: str
    escalated: bool
    reason: str
    device_used: str
    worker_audit_present: bool
    worker_audit_source: str
    worker_audit_missing_fields: Tuple[str, ...]
    payload: dict


@dataclass(frozen=True)
class ArtifactSet:
    json_paths: Tuple[Path, ...]
    markdown_paths: Tuple[Path, ...]
    csv_paths: Tuple[Path, ...]


@dataclass(frozen=True)
class ValidationCellArtifacts:
    cell: ValidationCell
    output_root: Path
    benchmark_artifacts: ArtifactSet
    adaptive_trace_paths: Tuple[Path, ...]
    collected_at: datetime


@dataclass(frozen=True)
class TraceSnapshot:
    timestamps_by_path: Dict[Path, int]


def benchmark_command() -> List[str]:
    if os.name == "nt" and shutil.which("py"):
        return ["py", "-3.13", str(REPO_ROOT / "scripts" / "run_dispatch_v2_benchmark.py")]
    return ["python", str(REPO_ROOT / "scripts" / "run_dispatch_v2_benchmark.py")]


def git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            check=False,
            capture_output=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
    except OSError:
        pass
    return "workspace"


def json_read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_snapshot(output_root: Path) -> ArtifactSet:
    if not output_root.exists():
        return ArtifactSet((), (), ())
    return ArtifactSet(
        tuple(sorted(output_root.glob("dispatch-quality*.json"))),
        tuple(sorted(output_root.glob("dispatch-quality*.md"))),
        tuple(sorted(output_root.glob("dispatch-quality*.csv"))),
    )


def trace_snapshot(output_root: Path) -> TraceSnapshot:
    if not output_root.exists():
        return TraceSnapshot({})
    timestamps_by_path = {}
    for path in sorted(output_root.rglob("*.json")):
        if "adaptive_compute_trace" not in {part.lower() for part in path.parts}:
            continue
        timestamps_by_path[path] = path.stat().st_mtime_ns
    return TraceSnapshot(timestamps_by_path)


def artifact_delta(before: ArtifactSet, after: ArtifactSet) -> ArtifactSet:
    return ArtifactSet(
        tuple(path for path in after.json_paths if path not in before.json_paths),
        tuple(path for path in after.markdown_paths if path not in before.markdown_paths),
        tuple(path for path in after.csv_paths if path not in before.csv_paths),
    )


def trace_delta(before: TraceSnapshot, after: TraceSnapshot) -> Tuple[Path, ...]:
    fresh_paths = []
    for path, modified_at_ns in after.timestamps_by_path.items():
        if path not in before.timestamps_by_path or modified_at_ns > before.timestamps_by_path[path]:
            fresh_paths.append(path)
    return tuple(fresh_paths)


def artifact_paths_repr(paths: Sequence[Path]) -> str:
    if not paths:
        return "[]"
    return "[" + ", ".join(str(path) for path in paths) + "]"


def artifact_last_modified_at(path: str) -> str:
    if not path:
        return ""
    artifact_path = Path(path)
    if not artifact_path.exists():
        return ""
    return datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=timezone.utc).isoformat()


def selected_target_cases(case_ids: Sequence[str]) -> List[Tuple[str, str]]:
    if not case_ids:
        return list(TARGET_CASES)
    indexed = {f"{scenario_pack}/{size}": (scenario_pack, size) for scenario_pack, size in TARGET_CASES}
    selected: List[Tuple[str, str]] = []
    for case_id in case_ids:
        if case_id not in indexed:
            raise ValueError(f"Unsupported target case '{case_id}'. Allowed: {', '.join(indexed)}")
        selected.append(indexed[case_id])
    return selected


def target_case_ids(target_cases: Sequence[Tuple[str, str]]) -> List[str]:
    return [f"{scenario_pack}/{size}" for scenario_pack, size in target_cases]


def route_focus_default_case_ids() -> List[str]:
    return target_case_ids(ROUTE_GENERATION_FOCUS_CASES)


def case_cells(mode: str,
               decision_mode: str,
               prompt_family: str,
               profile: str,
               target_cases: Sequence[Tuple[str, str]]) -> List[ValidationCell]:
    cells = [
        ValidationCell(
            scenario_pack=scenario_pack,
            size=size,
            baseline="C",
            decision_mode=decision_mode,
            prompt_family=prompt_family,
            execution_mode="controlled",
            profile=profile,
            root_type="adaptive",
        )
        for scenario_pack, size in target_cases
    ]
    if mode == "paired":
        cells.extend(
            ValidationCell(
                scenario_pack=scenario_pack,
                size=size,
                baseline="C",
                decision_mode=decision_mode,
                prompt_family=prompt_family,
                execution_mode="controlled",
                profile="",
                root_type="comparison",
            )
            for scenario_pack, size in target_cases
        )
    return cells


def run_validation_cell(cell: ValidationCell, output_dir: Path, runner=subprocess.run) -> int:
    command = benchmark_command() + [
        "--baseline", cell.baseline,
        "--size", cell.size,
        "--scenario-pack", cell.scenario_pack,
        "--decision-mode", cell.decision_mode,
        "--prompt-family", cell.prompt_family,
        "--execution-mode", cell.execution_mode,
        "--output-dir", str(output_dir),
    ]
    if cell.profile:
        command.extend(["--profile", cell.profile])
    completed = runner(command, cwd=REPO_ROOT, text=True, check=False)
    return int(completed.returncode)


def collect_benchmark_results_from_paths(paths: Sequence[Path], root_type: str, root_path: Path) -> Dict[Tuple[str, str, str, str, str], dict]:
    indexed: Dict[Tuple[str, str, str, str, str], dict] = {}
    latest_mtime_ns: Dict[Tuple[str, str, str, str, str], int] = {}
    for path in sorted(paths):
        payload = json_read(path)
        if "baselineId" not in payload:
            continue
        key = (
            str(payload.get("scenarioPack", "")),
            str(payload.get("workloadSize", "")),
            str(payload.get("executionMode", "")),
            str(payload.get("decisionMode", "")),
            str(payload.get("promptFamily", "v2")),
        )
        payload["_rootType"] = root_type
        payload["_rootPath"] = str(root_path)
        payload["_artifactPath"] = str(path)
        modified_at_ns = path.stat().st_mtime_ns
        if key not in indexed or modified_at_ns >= latest_mtime_ns.get(key, -1):
            indexed[key] = payload
            latest_mtime_ns[key] = modified_at_ns
    return indexed


def collect_benchmark_results(root: Path, root_type: str) -> Dict[Tuple[str, str, str, str, str], dict]:
    if not root.exists():
        return {}
    return collect_benchmark_results_from_paths(tuple(sorted(root.rglob("dispatch-quality*.json"))), root_type, root)


def parse_adaptive_trace(path: Path, root_type: str, root_path: Path) -> Optional[AdaptiveTraceRow]:
    parts = path.parts
    try:
        feedback_index = parts.index("feedback")
        decision_stage_index = parts.index("decision-stage")
    except ValueError:
        return None
    if decision_stage_index + 1 >= len(parts) or parts[decision_stage_index + 1] != "adaptive_compute_trace":
        return None
    payload = json_read(path)
    trace_id = str(payload.get("traceId", "")).strip()
    return AdaptiveTraceRow(
        root_type=root_type,
        root_path=str(root_path),
        scenario_pack=parts[feedback_index + 1],
        size=parts[feedback_index + 2].upper(),
        execution_mode=parts[feedback_index + 3],
        decision_mode=parts[feedback_index + 4],
        prompt_family=parts[feedback_index + 5],
        baseline=parts[feedback_index + 6].upper(),
        trace_id=trace_id,
        stage_name=str(payload.get("stageName", "")).strip(),
        worker_name=str(payload.get("workerName", "")).strip(),
        decision=str(payload.get("decision", "")).strip(),
        escalated=bool(payload.get("escalated")),
        reason=str(payload.get("reason", "")).strip(),
        device_used=str(payload.get("deviceUsed", "")).strip(),
        worker_audit_present=bool(payload.get("workerAuditPresent")),
        worker_audit_source=str(payload.get("workerAuditSource", "")).strip(),
        worker_audit_missing_fields=tuple(payload.get("workerAuditMissingFields", []) or []),
        payload=payload,
    )


def collect_adaptive_rows(root: Path, root_type: str) -> Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]]:
    indexed: Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]] = {}
    if not root.exists():
        return indexed
    latest_rows: Dict[Tuple[str, str, str, str, str, str, str], Tuple[int, AdaptiveTraceRow]] = {}
    for path in sorted(root.rglob("*.json")):
        row = parse_adaptive_trace(path, root_type, root)
        if row is None:
            continue
        row_key = (
            row.scenario_pack,
            row.size,
            row.execution_mode,
            row.decision_mode,
            row.prompt_family,
            row.stage_name,
            row.worker_name,
        )
        modified_at_ns = path.stat().st_mtime_ns
        if row_key not in latest_rows or modified_at_ns >= latest_rows[row_key][0]:
            latest_rows[row_key] = (modified_at_ns, row)
    for _, row in latest_rows.values():
        key = (row.scenario_pack, row.size, row.execution_mode, row.decision_mode, row.prompt_family)
        indexed.setdefault(key, []).append(row)
    return indexed


def collect_adaptive_rows_from_paths(paths: Sequence[Path], root_type: str, root_path: Path) -> Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]]:
    indexed: Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]] = {}
    latest_rows: Dict[Tuple[str, str, str, str, str, str, str], Tuple[int, AdaptiveTraceRow]] = {}
    for path in sorted(paths):
        row = parse_adaptive_trace(path, root_type, root_path)
        if row is None:
            continue
        row_key = (
            row.scenario_pack,
            row.size,
            row.execution_mode,
            row.decision_mode,
            row.prompt_family,
            row.stage_name,
            row.worker_name,
        )
        modified_at_ns = path.stat().st_mtime_ns
        if row_key not in latest_rows or modified_at_ns >= latest_rows[row_key][0]:
            latest_rows[row_key] = (modified_at_ns, row)
    for _, row in latest_rows.values():
        key = (row.scenario_pack, row.size, row.execution_mode, row.decision_mode, row.prompt_family)
        indexed.setdefault(key, []).append(row)
    return indexed


def filter_adaptive_rows(rows: Iterable[AdaptiveTraceRow],
                         target_cases: Sequence[Tuple[str, str]],
                         target_stages: Sequence[str]) -> List[AdaptiveTraceRow]:
    allowed_cases = {(scenario_pack, size) for scenario_pack, size in target_cases}
    allowed_stages = set(target_stages)
    filtered = [
        row for row in rows
        if (row.scenario_pack, row.size) in allowed_cases
        and (not allowed_stages or row.stage_name in allowed_stages)
    ]
    return filtered


def parse_instant(value: object) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def latency_ms(result: Optional[dict]) -> Optional[int]:
    if not result:
        return None
    started = parse_instant(result.get("cellStartedAt"))
    completed = parse_instant(result.get("dispatchCompletedAt")) or parse_instant(result.get("cellCompletedAt"))
    if started is None or completed is None:
        return None
    return int((completed - started).total_seconds() * 1000)


def worker_device_audit(result: Optional[dict]) -> List[dict]:
    if not result:
        return []
    workers = result.get("workerStatusSnapshot", [])
    if not isinstance(workers, list):
        return []
    return [
        {
            "workerName": worker.get("workerName", ""),
            "enabled": worker.get("enabled"),
            "ready": worker.get("ready"),
            "device": worker.get("device", ""),
            "dtype": worker.get("dtype", ""),
            "gpuMemoryAllocatedMb": worker.get("gpuMemoryAllocatedMb"),
            "batchSize": worker.get("batchSize"),
            "compileMode": worker.get("compileMode", ""),
            "modelLoaded": worker.get("modelLoaded"),
            "warmupDone": worker.get("warmupDone"),
            "workerAuditPresent": worker.get("workerAuditPresent"),
            "workerAuditSource": worker.get("workerAuditSource", ""),
            "workerAuditMissingFields": worker.get("workerAuditMissingFields", []),
            "applied": worker.get("applied"),
            "notAppliedReason": worker.get("notAppliedReason", ""),
        }
        for worker in workers
    ]


def classify_provider_failure(reason: str) -> str:
    normalized = (reason or "").strip().lower()
    if not normalized:
        return ""
    if "model-discovery" in normalized:
        return "model-discovery-failed"
    if "timeout" in normalized or "timed out" in normalized:
        return "timeout"
    if "schema" in normalized and ("invalid" in normalized or "validation" in normalized or "failed" in normalized):
        return "schema-invalid"
    if "empty" in normalized and ("response" in normalized or "provider" in normalized):
        return "empty-response"
    if "http-4" in normalized or "status=4" in normalized or "status:4" in normalized or "status 4" in normalized:
        return "http-4xx"
    if "http-5" in normalized or "status=5" in normalized or "status:5" in normalized or "status 5" in normalized:
        return "http-5xx"
    if "provider-http-error" in normalized or "http-error" in normalized:
        return "provider-http-error"
    return ""


def classify_stage_provider_failures(stage_fallback_summary: dict) -> Dict[str, str]:
    latest_reasons = stage_fallback_summary.get("latestFallbackReasonByStage", {})
    if not isinstance(latest_reasons, dict):
        return {}
    classified: Dict[str, str] = {}
    for stage_name, reason in latest_reasons.items():
        failure_class = classify_provider_failure(str(reason))
        if failure_class:
            classified[str(stage_name)] = failure_class
    return classified


def summarize_traces(rows: Iterable[AdaptiveTraceRow]) -> dict:
    worker_summary: Dict[str, dict] = {}
    stage_summary: Dict[str, dict] = {}
    total_rows = 0
    escalated_rows = 0
    skipped_rows = 0
    for row in rows:
        total_rows += 1
        escalated_rows += 1 if row.escalated else 0
        skipped_rows += 0 if row.escalated else 1
        worker_entry = worker_summary.setdefault(row.worker_name or "unknown-worker", {
            "totalDecisions": 0,
            "escalatedCount": 0,
            "skippedCount": 0,
            "reasons": {},
            "devicesUsed": set(),
            "auditSources": set(),
            "auditMissingFields": set(),
            "auditPresentCount": 0,
        })
        worker_entry["totalDecisions"] += 1
        worker_entry["escalatedCount"] += 1 if row.escalated else 0
        worker_entry["skippedCount"] += 0 if row.escalated else 1
        worker_entry["reasons"][row.reason or "unspecified"] = worker_entry["reasons"].get(row.reason or "unspecified", 0) + 1
        if row.device_used:
            worker_entry["devicesUsed"].add(row.device_used)
        if row.worker_audit_source:
            worker_entry["auditSources"].add(row.worker_audit_source)
        if row.worker_audit_present:
            worker_entry["auditPresentCount"] += 1
        worker_entry["auditMissingFields"].update(row.worker_audit_missing_fields)

        stage_entry = stage_summary.setdefault(row.stage_name or "unknown-stage", {
            "totalDecisions": 0,
            "escalatedCount": 0,
            "skippedCount": 0,
            "reasons": {},
            "auditMissingFields": set(),
        })
        stage_entry["totalDecisions"] += 1
        stage_entry["escalatedCount"] += 1 if row.escalated else 0
        stage_entry["skippedCount"] += 0 if row.escalated else 1
        stage_entry["reasons"][row.reason or "unspecified"] = stage_entry["reasons"].get(row.reason or "unspecified", 0) + 1
        stage_entry["auditMissingFields"].update(row.worker_audit_missing_fields)

    for entry in worker_summary.values():
        entry["devicesUsed"] = sorted(entry["devicesUsed"])
        entry["auditSources"] = sorted(entry["auditSources"])
        entry["auditMissingFields"] = sorted(entry["auditMissingFields"])
    for entry in stage_summary.values():
        entry["auditMissingFields"] = sorted(entry["auditMissingFields"])
    return {
        "totalAdaptiveDecisions": total_rows,
        "escalatedCount": escalated_rows,
        "skippedCount": skipped_rows,
        "workers": worker_summary,
        "stages": stage_summary,
    }


def benchmark_summary(result: Optional[dict]) -> dict:
    if not result:
        return {}
    artifact_path = str(result.get("_artifactPath", ""))
    metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
    stage_fallback_summary = result.get("stageFallbackSummary", {}) if isinstance(result.get("stageFallbackSummary"), dict) else {}
    provider_failure_classes = classify_stage_provider_failures(stage_fallback_summary)
    return {
        "artifactPath": artifact_path,
        "artifactLastModifiedAt": artifact_last_modified_at(artifact_path),
        "rootPath": result.get("_rootPath", ""),
        "mlAttachStatus": result.get("mlAttachStatus", ""),
        "timeoutPhase": result.get("timeoutPhase", ""),
        "notes": result.get("notes", []),
        "latencyMs": latency_ms(result),
        "selectedProposalCount": metrics.get("selectedProposalCount"),
        "executedAssignmentCount": metrics.get("executedAssignmentCount"),
        "robustUtilityAverage": metrics.get("robustUtilityAverage"),
        "selectorObjectiveValue": metrics.get("selectorObjectiveValue"),
        "workerFallbackRate": metrics.get("workerFallbackRate"),
        "routeGeometryCoverage": result.get("routeVectorMetrics", {}).get("geometryCoverage", None),
        "stageFallbackSummary": stage_fallback_summary,
        "providerFailureClassesByStage": provider_failure_classes,
        "providerFailureClasses": sorted(set(provider_failure_classes.values())),
        "workerDeviceAudit": worker_device_audit(result),
    }


def route_vector_availability(route_geometry_coverage: object) -> str:
    if not isinstance(route_geometry_coverage, (int, float)):
        return "unknown"
    if route_geometry_coverage <= 0:
        return "missing"
    if route_geometry_coverage >= 0.95:
        return "complete"
    return "partial"


def route_generation_focus_summary(adaptive_benchmark: dict, adaptive_rows: Sequence[AdaptiveTraceRow]) -> dict:
    routefinder_rows = [
        row for row in adaptive_rows
        if row.stage_name == "route-proposal-pool" or row.worker_name == "ml-routefinder-worker"
    ]
    stage_fallback_summary = adaptive_benchmark.get("stageFallbackSummary", {})
    latest_reasons = stage_fallback_summary.get("latestFallbackReasonByStage", {}) if isinstance(stage_fallback_summary, dict) else {}
    route_generation_reason = ""
    if isinstance(latest_reasons, dict):
        route_generation_reason = str(
            latest_reasons.get("ROUTE_GENERATION")
            or latest_reasons.get("route-generation")
            or "")
    route_geometry_coverage = adaptive_benchmark.get("routeGeometryCoverage")
    reasons: Dict[str, int] = {}
    devices = set()
    audit_missing_fields = set()
    for row in routefinder_rows:
        reasons[row.reason or "unspecified"] = reasons.get(row.reason or "unspecified", 0) + 1
        if row.device_used:
            devices.add(row.device_used)
        audit_missing_fields.update(row.worker_audit_missing_fields)
    return {
        "selectedProposalCount": adaptive_benchmark.get("selectedProposalCount"),
        "executedAssignmentCount": adaptive_benchmark.get("executedAssignmentCount"),
        "robustUtilityAverage": adaptive_benchmark.get("robustUtilityAverage"),
        "routeGeometryCoverage": route_geometry_coverage,
        "routeVectorAvailability": route_vector_availability(route_geometry_coverage),
        "routeGenerationFallbackReason": route_generation_reason,
        "routeGenerationProviderFailureClass": classify_provider_failure(route_generation_reason),
        "routeFinderDecisionCount": len(routefinder_rows),
        "routeFinderEscalatedCount": sum(1 for row in routefinder_rows if row.escalated),
        "routeFinderSkippedCount": sum(1 for row in routefinder_rows if not row.escalated),
        "routeFinderReasons": reasons,
        "routeFinderDevices": sorted(devices),
        "routeFinderAuditMissingFields": sorted(audit_missing_fields),
    }


def determine_verdict(adaptive_summary: dict,
                      comparison_summary: dict,
                      target_stages: Sequence[str]) -> Tuple[str, List[str]]:
    adaptive_benchmark = adaptive_summary.get("benchmark", {})
    adaptive_trace = adaptive_summary.get("adaptiveTrace", {})
    reasons: List[str] = []
    if not adaptive_benchmark:
        return "EVIDENCE_GAP", ["adaptive-benchmark-missing"]
    if not adaptive_benchmark.get("artifactPath"):
        return "EVIDENCE_GAP", ["fresh-artifact-missing"]
    if not adaptive_trace or adaptive_trace.get("totalAdaptiveDecisions", 0) == 0:
        return "EVIDENCE_GAP", ["adaptive-trace-missing"]
    if adaptive_benchmark.get("mlAttachStatus") == "ML_ATTACH_FAIL":
        return "REGRESSION_RISK", ["ml-attach-failed"]
    if adaptive_benchmark.get("timeoutPhase") not in (None, "", "NONE"):
        return "REGRESSION_RISK", [f"timeout:{adaptive_benchmark.get('timeoutPhase')}"]
    ready_workers_missing_audit = [
        worker["workerName"]
        for worker in adaptive_benchmark.get("workerDeviceAudit", [])
        if worker.get("enabled") and worker.get("ready") and not worker.get("workerAuditPresent")
    ]
    if ready_workers_missing_audit:
        return "PASS_WITH_LIMITS", [f"worker-audit-missing:{','.join(sorted(ready_workers_missing_audit))}"]
    if any(
            "worker-device-audit-missing" in summary.get("reasons", {})
            for summary in adaptive_trace.get("workers", {}).values()):
        return "PASS_WITH_LIMITS", ["worker-device-audit-missing-observed"]
    if int(adaptive_benchmark.get("selectedProposalCount") or 0) <= 0:
        return "REGRESSION_RISK", ["selected-proposals-empty"]
    if int(adaptive_benchmark.get("executedAssignmentCount") or 0) <= 0:
        reasons.append("executed-assignments-empty")
    if target_stages:
        if adaptive_trace.get("totalAdaptiveDecisions", 0) <= 0:
            return "EVIDENCE_GAP", ["target-stage-trace-missing"]
        if adaptive_trace.get("skippedCount", 0) > 0 or adaptive_trace.get("escalatedCount", 0) > 0:
            reasons.append("target-stage-policy-observed")
            return "PASS", reasons
        return "PASS_WITH_LIMITS", reasons or ["target-stage-observed-without-policy-decision"]
    if comparison_summary:
        adaptive_latency = adaptive_benchmark.get("latencyMs")
        comparison_latency = comparison_summary.get("latencyMs")
        adaptive_robust = adaptive_benchmark.get("robustUtilityAverage")
        comparison_robust = comparison_summary.get("robustUtilityAverage")
        adaptive_exec = int(adaptive_benchmark.get("executedAssignmentCount") or 0)
        comparison_exec = int(comparison_summary.get("executedAssignmentCount") or 0)
        if comparison_exec > adaptive_exec:
            return "REGRESSION_RISK", ["executed-assignment-regressed"]
        if isinstance(adaptive_robust, (int, float)) and isinstance(comparison_robust, (int, float)) and adaptive_robust < comparison_robust - 0.05:
            return "REGRESSION_RISK", ["robust-utility-regressed"]
        if adaptive_latency is not None and comparison_latency is not None and adaptive_latency <= comparison_latency:
            reasons.append("latency-not-worse-than-comparison")
        else:
            reasons.append("latency-improvement-not-proven")
        if adaptive_trace.get("skippedCount", 0) > 0:
            reasons.append("adaptive-skip-observed")
            return "PASS", reasons
        return "PASS_WITH_LIMITS", reasons
    if adaptive_trace.get("skippedCount", 0) > 0:
        return "PASS", ["adaptive-skip-observed"]
    return "PASS_WITH_LIMITS", reasons or ["adaptive-skip-not-observed"]


def build_case_report(
    scenario_pack: str,
    size: str,
    decision_mode: str,
    prompt_family: str,
    adaptive_results: Dict[Tuple[str, str, str, str, str], dict],
    comparison_results: Dict[Tuple[str, str, str, str, str], dict],
    adaptive_traces: Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]],
    target_stages: Sequence[str],
) -> dict:
    key = (scenario_pack, size, "controlled", decision_mode, prompt_family)
    adaptive_result = adaptive_results.get(key)
    comparison_result = comparison_results.get(key)
    adaptive_rows = adaptive_traces.get(key, [])
    adaptive_summary = {
        "benchmark": benchmark_summary(adaptive_result),
        "adaptiveTrace": summarize_traces(adaptive_rows),
    }
    route_focus = route_generation_focus_summary(adaptive_summary["benchmark"], adaptive_rows)
    comparison_summary = benchmark_summary(comparison_result)
    verdict, reasons = determine_verdict(adaptive_summary, comparison_summary, target_stages)
    return {
        "caseId": f"{scenario_pack}/{size}/controlled/{decision_mode}/{prompt_family}",
        "scenarioPack": scenario_pack,
        "workloadSize": size,
        "executionMode": "controlled",
        "decisionMode": decision_mode,
        "promptFamily": prompt_family,
        "adaptive": adaptive_summary,
        "comparison": comparison_summary,
        "routeGenerationFocus": route_focus,
        "targetStages": list(target_stages),
        "verdict": verdict,
        "verdictReasons": reasons,
    }


def report_stem(target_stages: Sequence[str]) -> str:
    if not target_stages:
        return "full_adaptive_validation"
    return "targeted_adaptive_closure-" + "__".join(stage.replace("/", "-") for stage in target_stages)


def report_title(payload: dict) -> str:
    if payload.get("routeGenerationFocus"):
        return "# Route Generation Focus Report"
    if payload.get("targetStages"):
        return "# Targeted Adaptive Closure Report"
    return "# Full Adaptive Validation Report"


def markdown_report(payload: dict) -> str:
    lines = [
        report_title(payload),
        "",
        f"- generatedAt: `{payload['generatedAt']}`",
        f"- validationCommit: `{payload['validationCommit']}`",
        f"- mode: `{payload['mode']}`",
        f"- decisionMode: `{payload['decisionMode']}`",
        f"- promptFamily: `{payload['promptFamily']}`",
        f"- adaptiveProfile: `{payload['adaptiveProfile']}`",
        f"- adaptiveRoots: `{', '.join(payload['adaptiveRoots']) or 'none'}`",
        f"- comparisonRoots: `{', '.join(payload['comparisonRoots']) or 'none'}`",
        f"- targetStages: `{payload.get('targetStages', [])}`",
        f"- targetCases: `{payload.get('targetCases', [])}`",
        f"- routeGenerationFocus: `{payload.get('routeGenerationFocus', False)}`",
        f"- rerunExecuted: `{payload['rerunExecuted']}`",
        "",
        "## Case Verdicts",
        "",
        "| case | verdict | adaptive latency ms | comparison latency ms | adaptive selected | adaptive executed | adaptive skipped | adaptive escalated |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in payload["cases"]:
        adaptive_benchmark = case["adaptive"]["benchmark"]
        adaptive_trace = case["adaptive"]["adaptiveTrace"]
        comparison = case["comparison"]
        lines.append(
            f"| `{case['scenarioPack']}` | `{case['verdict']}` | "
            f"{adaptive_benchmark.get('latencyMs', 'n/a')} | "
            f"{comparison.get('latencyMs', 'n/a')} | "
            f"{adaptive_benchmark.get('selectedProposalCount', 'n/a')} | "
            f"{adaptive_benchmark.get('executedAssignmentCount', 'n/a')} | "
            f"{adaptive_trace.get('skippedCount', 0)} | "
            f"{adaptive_trace.get('escalatedCount', 0)} |"
        )
    lines.extend(["", "## Details", ""])
    for case in payload["cases"]:
        adaptive_benchmark = case["adaptive"]["benchmark"]
        adaptive_trace = case["adaptive"]["adaptiveTrace"]
        lines.append(f"### `{case['scenarioPack']}`")
        lines.append(f"- verdict: `{case['verdict']}` reasons=`{case['verdictReasons']}`")
        lines.append(
            f"- adaptive benchmark: latencyMs=`{adaptive_benchmark.get('latencyMs', 'n/a')}` "
            f"selected=`{adaptive_benchmark.get('selectedProposalCount', 'n/a')}` "
            f"executed=`{adaptive_benchmark.get('executedAssignmentCount', 'n/a')}` "
            f"robustUtility=`{adaptive_benchmark.get('robustUtilityAverage', 'n/a')}` "
            f"mlAttachStatus=`{adaptive_benchmark.get('mlAttachStatus', 'n/a')}`"
        )
        if adaptive_benchmark.get("artifactPath"):
            lines.append(
                f"- adaptive artifact: path=`{adaptive_benchmark.get('artifactPath')}` "
                f"modifiedAt=`{adaptive_benchmark.get('artifactLastModifiedAt', '')}` "
                f"root=`{adaptive_benchmark.get('rootPath', '')}`"
            )
        lines.append(
            f"- adaptive trace: total=`{adaptive_trace.get('totalAdaptiveDecisions', 0)}` "
            f"skipped=`{adaptive_trace.get('skippedCount', 0)}` "
            f"escalated=`{adaptive_trace.get('escalatedCount', 0)}`"
        )
        route_focus = case.get("routeGenerationFocus", {})
        if payload.get("routeGenerationFocus") and route_focus:
            lines.append(
                f"- route generation: routeVector=`{route_focus.get('routeVectorAvailability')}` "
                f"geometryCoverage=`{route_focus.get('routeGeometryCoverage', 'n/a')}` "
                f"routeFinderDecisions=`{route_focus.get('routeFinderDecisionCount', 0)}` "
                f"routeFinderEscalated=`{route_focus.get('routeFinderEscalatedCount', 0)}` "
                f"routeFinderSkipped=`{route_focus.get('routeFinderSkippedCount', 0)}` "
                f"routeFinderReasons=`{route_focus.get('routeFinderReasons', {})}`"
            )
            lines.append(
                f"- route fallback: reason=`{route_focus.get('routeGenerationFallbackReason', '')}` "
                f"providerClass=`{route_focus.get('routeGenerationProviderFailureClass', '')}`"
            )
        if adaptive_benchmark.get("providerFailureClassesByStage"):
            lines.append(
                f"- provider failures: classesByStage=`{adaptive_benchmark.get('providerFailureClassesByStage', {})}`"
            )
        comparison = case["comparison"]
        if comparison:
            lines.append(
                f"- comparison benchmark: latencyMs=`{comparison.get('latencyMs', 'n/a')}` "
                f"selected=`{comparison.get('selectedProposalCount', 'n/a')}` "
                f"executed=`{comparison.get('executedAssignmentCount', 'n/a')}` "
                f"robustUtility=`{comparison.get('robustUtilityAverage', 'n/a')}`"
            )
            if comparison.get("artifactPath"):
                lines.append(
                    f"- comparison artifact: path=`{comparison.get('artifactPath')}` "
                    f"modifiedAt=`{comparison.get('artifactLastModifiedAt', '')}` "
                    f"root=`{comparison.get('rootPath', '')}`"
                )
        for worker_name, summary in sorted(adaptive_trace.get("workers", {}).items()):
            lines.append(
                f"- worker `{worker_name}` decisions=`{summary['totalDecisions']}` "
                f"escalated=`{summary['escalatedCount']}` skipped=`{summary['skippedCount']}` "
                f"devices=`{summary['devicesUsed']}` auditSources=`{summary['auditSources']}` "
                f"auditMissingFields=`{summary['auditMissingFields']}` reasons=`{summary['reasons']}`"
            )
        if adaptive_benchmark.get("workerDeviceAudit"):
            for worker in adaptive_benchmark["workerDeviceAudit"]:
                lines.append(
                    f"- device audit `{worker['workerName']}` enabled=`{worker['enabled']}` ready=`{worker['ready']}` "
                    f"device=`{worker['device']}` dtype=`{worker['dtype']}` "
                    f"gpuMemoryAllocatedMb=`{worker['gpuMemoryAllocatedMb']}` batchSize=`{worker['batchSize']}` "
                    f"compileMode=`{worker['compileMode']}` workerAuditPresent=`{worker['workerAuditPresent']}` "
                    f"workerAuditSource=`{worker['workerAuditSource']}` "
                    f"workerAuditMissingFields=`{worker['workerAuditMissingFields']}` applied=`{worker['applied']}`"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(payload: dict, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stem = report_stem(payload.get("targetStages", []))
    json_path = output_dir / f"{stem}-{timestamp}.json"
    markdown_path = output_dir / f"{stem}_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(payload), encoding="utf-8")
    return json_path, markdown_path


def collect_case_reports(
    adaptive_roots: Sequence[Path],
    comparison_roots: Sequence[Path],
    decision_mode: str,
    prompt_family: str,
    target_cases: Sequence[Tuple[str, str]],
    target_stages: Sequence[str],
    rerun_artifacts: Optional[Sequence[ValidationCellArtifacts]] = None,
) -> List[dict]:
    adaptive_results: Dict[Tuple[str, str, str, str, str], dict] = {}
    adaptive_trace_index: Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]] = {}
    comparison_results: Dict[Tuple[str, str, str, str, str], dict] = {}
    if rerun_artifacts and not target_stages:
        for artifact_group in rerun_artifacts:
            if artifact_group.cell.root_type == "adaptive":
                adaptive_results.update(collect_benchmark_results_from_paths(
                    artifact_group.benchmark_artifacts.json_paths,
                    "adaptive",
                    artifact_group.output_root,
                ))
                for key, rows in collect_adaptive_rows_from_paths(
                        artifact_group.adaptive_trace_paths,
                        "adaptive",
                        artifact_group.output_root).items():
                    adaptive_trace_index.setdefault(
                        key,
                        []).extend(filter_adaptive_rows(rows, target_cases, target_stages))
            else:
                comparison_results.update(collect_benchmark_results_from_paths(
                    artifact_group.benchmark_artifacts.json_paths,
                    "comparison",
                    artifact_group.output_root,
                ))
    else:
        for root in adaptive_roots:
            adaptive_results.update(collect_benchmark_results(root, "adaptive"))
            for key, rows in collect_adaptive_rows(root, "adaptive").items():
                adaptive_trace_index.setdefault(
                    key,
                    []).extend(filter_adaptive_rows(rows, target_cases, target_stages))
        for root in comparison_roots:
            comparison_results.update(collect_benchmark_results(root, "comparison"))
        if rerun_artifacts and target_stages:
            for artifact_group in rerun_artifacts:
                if artifact_group.cell.root_type == "adaptive":
                    adaptive_results.update(collect_benchmark_results_from_paths(
                        artifact_group.benchmark_artifacts.json_paths,
                        "adaptive",
                        artifact_group.output_root,
                    ))
                    for key, rows in collect_adaptive_rows_from_paths(
                            artifact_group.adaptive_trace_paths,
                            "adaptive",
                            artifact_group.output_root).items():
                        adaptive_trace_index.setdefault(
                            key,
                            []).extend(filter_adaptive_rows(rows, target_cases, target_stages))
                else:
                    comparison_results.update(collect_benchmark_results_from_paths(
                        artifact_group.benchmark_artifacts.json_paths,
                        "comparison",
                        artifact_group.output_root,
                    ))
    return [
        build_case_report(
            scenario_pack,
            size,
            decision_mode,
            prompt_family,
            adaptive_results,
            comparison_results,
            adaptive_trace_index,
            target_stages)
        for scenario_pack, size in target_cases
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 full-adaptive validation evidence rail.")
    parser.add_argument("--adaptive-root", action="append", default=[])
    parser.add_argument("--comparison-root", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--mode", choices=("adaptive-only", "paired"), default="paired")
    parser.add_argument("--decision-mode", choices=("legacy",), default="legacy")
    parser.add_argument("--prompt-family", choices=("v2", "v3"), default="v2")
    parser.add_argument("--profile", default="dispatch-v2-full-adaptive")
    parser.add_argument("--target-case", action="append", default=[], help="Optional case filter: normal-clear/S, heavy-rain/S, traffic-shock/S, forecast-heavy/S")
    parser.add_argument("--target-stage", action="append", default=[], choices=TARGET_STAGE_CHOICES)
    parser.add_argument("--route-generation-focus", action="store_true", help="Default to heavy-rain/S and traffic-shock/S route-proposal-pool evidence.")
    parser.add_argument("--rerun-cells", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    adaptive_roots = [Path(path) for path in args.adaptive_root]
    comparison_roots = [Path(path) for path in args.comparison_root]
    requested_target_cases = list(args.target_case)
    requested_target_stages = list(args.target_stage)
    if args.route_generation_focus:
        if not requested_target_cases:
            requested_target_cases = route_focus_default_case_ids()
        if not requested_target_stages:
            requested_target_stages = ["route-proposal-pool"]
    target_cases = selected_target_cases(requested_target_cases)
    target_stages = tuple(dict.fromkeys(stage for stage in requested_target_stages if stage))
    cells = case_cells(args.mode, args.decision_mode, args.prompt_family, args.profile, target_cases)
    print(f"[FULL ADAPTIVE VALIDATION] case-count={len(cells)}")
    for cell in cells:
        print(
            f"- root-type={cell.root_type} scenario-pack={cell.scenario_pack} size={cell.size} "
            f"decision-mode={cell.decision_mode} prompt-family={cell.prompt_family} "
            f"execution-mode={cell.execution_mode} profile={cell.profile or 'default'}"
        )
    if target_stages:
        print(f"- target-stages={list(target_stages)}")
    if requested_target_cases:
        print(f"- target-cases={list(requested_target_cases)}")
    if args.route_generation_focus:
        print("- route-generation-focus=True")
    if args.dry_run:
        return 0

    rerun_executed = False
    rerun_artifacts: List[ValidationCellArtifacts] = []
    if args.rerun_cells:
        rerun_executed = True
        for cell in cells:
            if target_stages:
                stage_root = "__".join(target_stages)
                root_name = "full-adaptive" if cell.root_type == "adaptive" else "pre-adaptive"
                live_root = output_dir / "fresh" / stage_root / root_name
            else:
                live_root = output_dir / "live" / ("full-adaptive" if cell.root_type == "adaptive" else "pre-adaptive")
            if cell.root_type == "adaptive":
                if live_root not in adaptive_roots:
                    adaptive_roots.append(live_root)
            else:
                if live_root not in comparison_roots:
                    comparison_roots.append(live_root)
            print(f"[CELL STARTED] root-type={cell.root_type} scenario-pack={cell.scenario_pack}")
            before_artifacts = artifact_snapshot(live_root)
            before_traces = trace_snapshot(live_root) if cell.root_type == "adaptive" else TraceSnapshot({})
            exit_code = run_validation_cell(cell, live_root)
            if exit_code != 0:
                print(f"[CELL FAILED] root-type={cell.root_type} scenario-pack={cell.scenario_pack} exit={exit_code}")
                return exit_code
            after_artifacts = artifact_snapshot(live_root)
            delta = artifact_delta(before_artifacts, after_artifacts)
            if not delta.json_paths:
                print(
                    f"[CELL FAILED] root-type={cell.root_type} scenario-pack={cell.scenario_pack} "
                    f"completed without fresh benchmark JSON artifacts "
                    f"output-root={live_root} before-json={len(before_artifacts.json_paths)} "
                    f"after-json={len(after_artifacts.json_paths)}"
                )
                return 1
            if not delta.markdown_paths:
                print(
                    f"[CELL FAILED] root-type={cell.root_type} scenario-pack={cell.scenario_pack} "
                    f"completed without fresh benchmark Markdown artifacts "
                    f"output-root={live_root} before-md={len(before_artifacts.markdown_paths)} "
                    f"after-md={len(after_artifacts.markdown_paths)}"
                )
                return 1
            trace_paths = ()
            if cell.root_type == "adaptive":
                trace_paths = trace_delta(before_traces, trace_snapshot(live_root))
            rerun_artifacts.append(ValidationCellArtifacts(
                cell=cell,
                output_root=live_root,
                benchmark_artifacts=delta,
                adaptive_trace_paths=trace_paths,
                collected_at=datetime.now(timezone.utc),
            ))
            print(f"[CELL COMPLETED] root-type={cell.root_type} scenario-pack={cell.scenario_pack}")
            print(
                f"[CELL ARTIFACT PATHS] root-type={cell.root_type} scenario-pack={cell.scenario_pack} "
                f"benchmark-json={artifact_paths_repr(delta.json_paths)} "
                f"benchmark-md={artifact_paths_repr(delta.markdown_paths)} "
                f"trace-json={artifact_paths_repr(trace_paths)} "
                f"report-input-root={live_root}"
            )

    cases = collect_case_reports(
        adaptive_roots,
        comparison_roots,
        args.decision_mode,
        args.prompt_family,
        target_cases,
        target_stages,
        rerun_artifacts=rerun_artifacts if rerun_executed else None,
    )
    payload = {
        "schemaVersion": "dispatch-full-adaptive-validation/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "validationCommit": git_commit(),
        "mode": args.mode,
        "decisionMode": args.decision_mode,
        "promptFamily": args.prompt_family,
        "adaptiveProfile": args.profile,
        "adaptiveRoots": [str(path) for path in adaptive_roots],
        "comparisonRoots": [str(path) for path in comparison_roots],
        "targetStages": list(target_stages),
        "targetCases": [f"{scenario_pack}/{size}" for scenario_pack, size in target_cases],
        "routeGenerationFocus": bool(args.route_generation_focus),
        "rerunExecuted": rerun_executed,
        "cases": cases,
        "verdicts": list(VERDICTS),
    }
    json_path, markdown_path = write_report(payload, output_dir)
    print(f"[REPORT JSON] {json_path}")
    print(f"[REPORT MARKDOWN] {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
