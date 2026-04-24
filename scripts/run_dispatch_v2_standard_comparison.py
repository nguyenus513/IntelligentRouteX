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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "standard-comparison"
DEFAULT_SCENARIOS = ("normal-clear", "heavy-rain", "traffic-shock", "forecast-heavy")
STANDARD_SCENARIOS = (
    "normal-clear",
    "heavy-rain",
    "traffic-shock",
    "forecast-heavy",
    "weekday-lunch-burst",
    "dinner-peak-high-density",
    "driver-scarcity",
    "route-ambiguity",
    "single-order-simple",
)
DEFAULT_PROFILES = (
    "heuristic-only",
    "ml-only",
    "full-adaptive",
    "llm-shadow",
    "llm-authoritative-gated",
)
LIGHT_PROFILES = ("heuristic-only", "ml-only", "full-adaptive")
LLM_PROFILES = ("llm-shadow", "llm-authoritative-gated")
VERDICTS = ("PASS", "PASS_WITH_LIMITS", "EVIDENCE_GAP", "FAIL")


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    baseline: str
    decision_mode: str
    prompt_family: str = "v2"
    execution_mode: str = "controlled"
    profile: str = ""
    authoritative_stages: Tuple[str, ...] = ()
    requires_llm: bool = False
    timeout_seconds: int = 180


@dataclass(frozen=True)
class StandardCell:
    scenario_pack: str
    size: str
    profile: ProfileSpec

    @property
    def cell_id(self) -> str:
        return f"{self.scenario_pack}/{self.size}/{self.profile.name}"


@dataclass(frozen=True)
class CellRunResult:
    cell: StandardCell
    verdict: str
    verdict_reasons: Tuple[str, ...]
    output_root: Path
    artifact_path: Optional[Path]
    return_code: Optional[int]
    timed_out: bool
    benchmark: Dict[str, object]
    decision_log: Dict[str, object]


PROFILE_SPECS: Dict[str, ProfileSpec] = {
    "heuristic-only": ProfileSpec("heuristic-only", baseline="A", decision_mode="legacy", timeout_seconds=120),
    "heuristic-ortools": ProfileSpec("heuristic-ortools", baseline="B", decision_mode="legacy", timeout_seconds=120),
    "ml-only": ProfileSpec("ml-only", baseline="C", decision_mode="legacy", timeout_seconds=180),
    "full-adaptive": ProfileSpec(
        "full-adaptive",
        baseline="C",
        decision_mode="legacy",
        profile="dispatch-v2-full-adaptive",
        timeout_seconds=180,
    ),
    "llm-shadow": ProfileSpec(
        "llm-shadow",
        baseline="C",
        decision_mode="llm-shadow",
        profile="dispatch-v2-full-adaptive",
        requires_llm=True,
        timeout_seconds=180,
    ),
    "llm-authoritative-gated": ProfileSpec(
        "llm-authoritative-gated",
        baseline="C",
        decision_mode="llm-authoritative",
        profile="dispatch-v2-full-adaptive",
        authoritative_stages=("route-critique", "final-selection"),
        requires_llm=True,
        timeout_seconds=240,
    ),
}


def python_command() -> List[str]:
    if os.name == "nt" and shutil.which("py"):
        return ["py", "-3.13"]
    return ["python"]


def benchmark_command(cell: StandardCell, output_dir: Path) -> List[str]:
    spec = cell.profile
    command = python_command() + [
        str(REPO_ROOT / "scripts" / "run_dispatch_v2_benchmark.py"),
        "--baseline", spec.baseline,
        "--size", cell.size,
        "--scenario-pack", cell.scenario_pack,
        "--decision-mode", spec.decision_mode,
        "--prompt-family", spec.prompt_family,
        "--execution-mode", spec.execution_mode,
        "--output-dir", str(output_dir),
    ]
    if spec.profile:
        command.extend(["--profile", spec.profile])
    for stage in spec.authoritative_stages:
        command.extend(["--authoritative-stage", stage])
    return command


def probe_command(output_root: Path) -> List[str]:
    return python_command() + [
        str(REPO_ROOT / "scripts" / "probe_llm_provider_responses.py"),
        "--output-dir", str(output_root / "provider-preflight"),
        "--model", "cx/gpt-5.5",
        "--model", "cx/gpt-5.4",
    ]


def split_csv(value: str) -> Tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def selected_scenarios(matrix: str, override: str) -> Tuple[str, ...]:
    if override:
        return split_csv(override)
    if matrix in ("local-minimum", "ml-only-4case", "llm-gated"):
        return DEFAULT_SCENARIOS
    if matrix == "standard-v1":
        return STANDARD_SCENARIOS
    raise ValueError(f"Unsupported matrix '{matrix}'.")


def selected_profiles(matrix: str, override: str) -> Tuple[str, ...]:
    names = split_csv(override) if override else {
        "local-minimum": DEFAULT_PROFILES,
        "ml-only-4case": LIGHT_PROFILES,
        "llm-gated": LLM_PROFILES,
        "standard-v1": DEFAULT_PROFILES,
    }.get(matrix)
    if names is None:
        raise ValueError(f"Unsupported matrix '{matrix}'.")
    unknown = [name for name in names if name not in PROFILE_SPECS]
    if unknown:
        raise ValueError(f"Unsupported profile(s): {', '.join(unknown)}")
    return tuple(names)


def selected_sizes(matrix: str, override: str) -> Tuple[str, ...]:
    if override:
        return split_csv(override)
    return ("S", "M") if matrix == "standard-v1" else ("S",)


def planned_cells(matrix: str, scenario_override: str = "", profile_override: str = "", size_override: str = "") -> List[StandardCell]:
    scenarios = selected_scenarios(matrix, scenario_override)
    profiles = selected_profiles(matrix, profile_override)
    sizes = selected_sizes(matrix, size_override)
    return [
        StandardCell(scenario, size, PROFILE_SPECS[profile])
        for scenario in scenarios
        for size in sizes
        for profile in profiles
    ]


def safe_path_part(value: str) -> str:
    return value.replace("/", "-").replace("\\", "-").replace(":", "-")


def cell_output_root(output_root: Path, cell: StandardCell) -> Path:
    return output_root / "live" / safe_path_part(cell.profile.name) / safe_path_part(cell.scenario_pack) / cell.size.lower()


def newest_dispatch_artifact(output_dir: Path) -> Optional[Path]:
    paths = sorted(output_dir.glob("dispatch-quality*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return paths[0] if paths else None


def read_json(path: Optional[Path]) -> Dict[str, object]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def decision_log_path(output_dir: Path, payload: Dict[str, object]) -> Path:
    scenario = str(payload.get("scenarioPack", "unknown"))
    size = str(payload.get("workloadSize", "S")).lower()
    execution_mode = str(payload.get("executionMode", "controlled"))
    decision_mode = str(payload.get("decisionMode", "legacy"))
    prompt_family = str(payload.get("promptFamily", "v2"))
    baseline = str(payload.get("baselineId", "C")).lower()
    return output_dir / "feedback" / scenario / size / execution_mode / decision_mode / prompt_family / baseline / "decision-log" / f"quality-{scenario}-{size}-{decision_mode}-{prompt_family}-{baseline}.json"


def load_decision_log(output_dir: Path, payload: Dict[str, object]) -> Dict[str, object]:
    path = decision_log_path(output_dir, payload)
    if not path.exists():
        return {}
    return read_json(path)


def elapsed_ms(payload: Dict[str, object]) -> Optional[int]:
    started = payload.get("cellStartedAt")
    completed = payload.get("cellCompletedAt") or payload.get("dispatchCompletedAt")
    if not isinstance(started, str) or not isinstance(completed, str):
        return None
    try:
        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(completed.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((end_dt - start_dt).total_seconds() * 1000))


def extract_failure_classes(payload: Dict[str, object]) -> Tuple[str, ...]:
    classes: List[str] = []
    for value in payload.get("degradeReasons", []) or []:
        if isinstance(value, str):
            classes.append(value)
    stage_summary = payload.get("stageFallbackSummary", {})
    if isinstance(stage_summary, dict):
        latest = stage_summary.get("latestFallbackReasonByStage", {})
        if isinstance(latest, dict):
            classes.extend(str(value) for value in latest.values() if value)
    blockers = payload.get("promotionBlockers", []) or []
    for blocker in blockers:
        if isinstance(blocker, str):
            classes.append(blocker)
        elif isinstance(blocker, dict):
            stage_name = blocker.get("stageName", "unknown-stage")
            blocker_reasons = blocker.get("blockerReasons", [])
            if isinstance(blocker_reasons, list):
                classes.extend(f"{stage_name}:{reason}" for reason in blocker_reasons if reason)
            elif blocker_reasons:
                classes.append(f"{stage_name}:{blocker_reasons}")
    return tuple(dict.fromkeys(classes))


def classify_artifact(payload: Dict[str, object]) -> Tuple[str, Tuple[str, ...]]:
    if not payload:
        return "EVIDENCE_GAP", ("missing-benchmark-artifact",)
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        return "FAIL", ("missing-metrics",)
    if metrics.get("executionValid") is False or metrics.get("conflictFreeAssignments") is False:
        return "FAIL", ("invalid-or-conflicting-execution",)
    reasons = list(extract_failure_classes(payload))
    stage_summary = payload.get("stageFallbackSummary", {})
    total_fallbacks = stage_summary.get("totalFallbacks", 0) if isinstance(stage_summary, dict) else 0
    worker_fallback_rate = metrics.get("workerFallbackRate", 0)
    timeout_phase = payload.get("timeoutPhase")
    if timeout_phase and str(timeout_phase).upper() != "NONE":
        return "EVIDENCE_GAP", (f"timeout-phase:{timeout_phase}",)
    if total_fallbacks or worker_fallback_rate or reasons:
        if not reasons:
            reasons.append("fallback-or-degrade-observed")
        return "PASS_WITH_LIMITS", tuple(dict.fromkeys(reasons))
    return "PASS", ("quality-artifact-valid",)


def llm_preflight_ready(output_root: Path, runner=subprocess.run, skip: bool = False) -> Tuple[bool, str]:
    if skip:
        return True, "skipped-by-user"
    completed = runner(probe_command(output_root), cwd=REPO_ROOT, text=True, check=False)
    if completed.returncode == 0:
        return True, "provider-responses-ready"
    return False, "provider-responses-not-ready"


def run_standard_cell(
        cell: StandardCell,
        output_root: Path,
        provider_ready: bool,
        provider_reason: str,
        runner=subprocess.run) -> CellRunResult:
    output_dir = cell_output_root(output_root, cell)
    if cell.profile.requires_llm and not provider_ready:
        return CellRunResult(
            cell, "EVIDENCE_GAP", (provider_reason,), output_dir, None, None, False, {}, {})
    output_dir.mkdir(parents=True, exist_ok=True)
    command = benchmark_command(cell, output_dir)
    try:
        completed = runner(
            command,
            cwd=REPO_ROOT,
            text=True,
            check=False,
            timeout=cell.profile.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return CellRunResult(
            cell, "EVIDENCE_GAP", ("benchmark-timeout",), output_dir, None, None, True, {}, {})
    artifact_path = newest_dispatch_artifact(output_dir)
    payload = read_json(artifact_path)
    decision_log = load_decision_log(output_dir, payload)
    if completed.returncode != 0:
        reasons = (f"benchmark-return-code:{completed.returncode}",)
        verdict = "FAIL" if not cell.profile.requires_llm else "EVIDENCE_GAP"
        return CellRunResult(cell, verdict, reasons, output_dir, artifact_path, completed.returncode, False, payload, decision_log)
    verdict, reasons = classify_artifact(payload)
    return CellRunResult(cell, verdict, reasons, output_dir, artifact_path, completed.returncode, False, payload, decision_log)


def summarize_stage_latencies(decision_log: Dict[str, object]) -> Dict[str, int]:
    rows = decision_log.get("stageLatencies", []) if decision_log else []
    result: Dict[str, int] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if isinstance(row, dict) and row.get("stageName"):
            result[str(row["stageName"])] = int(row.get("elapsedMs", 0) or 0)
    return result


def summarize_ml_invocations(decision_log: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    rows = decision_log.get("mlStageMetadata", []) if decision_log else []
    summary: Dict[str, Dict[str, object]] = {}
    if not isinstance(rows, list):
        return summary
    for row in rows:
        if not isinstance(row, dict):
            continue
        model = str(row.get("sourceModel", "unknown"))
        item = summary.setdefault(model, {"count": 0, "latencyMs": 0, "fallbacks": 0})
        item["count"] = int(item["count"]) + 1
        item["latencyMs"] = int(item["latencyMs"]) + int(row.get("latencyMs", 0) or 0)
        if row.get("fallbackUsed"):
            item["fallbacks"] = int(item["fallbacks"]) + 1
    return summary


def cell_report_row(result: CellRunResult) -> Dict[str, object]:
    payload = result.benchmark
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
    route_metrics = payload.get("routeVectorMetrics", {}) if isinstance(payload.get("routeVectorMetrics", {}), dict) else {}
    route_budget_metrics = payload.get("routeProposalBudgetMetrics", {}) if isinstance(payload.get("routeProposalBudgetMetrics", {}), dict) else {}
    token_usage = payload.get("tokenUsageSummary", {}) if isinstance(payload.get("tokenUsageSummary", {}), dict) else {}
    stage_summary = payload.get("stageFallbackSummary", {}) if isinstance(payload.get("stageFallbackSummary", {}), dict) else {}
    return {
        "scenarioPack": result.cell.scenario_pack,
        "size": result.cell.size,
        "profile": result.cell.profile.name,
        "baseline": result.cell.profile.baseline,
        "decisionMode": result.cell.profile.decision_mode,
        "promptFamily": result.cell.profile.prompt_family,
        "runtimeProfile": result.cell.profile.profile or "default",
        "verdict": result.verdict,
        "verdictReasons": list(result.verdict_reasons),
        "outputRoot": str(result.output_root),
        "artifactPath": str(result.artifact_path) if result.artifact_path else "",
        "returnCode": result.return_code,
        "timedOut": result.timed_out,
        "totalLatencyMs": elapsed_ms(payload),
        "executedAssignmentCount": metrics.get("executedAssignmentCount"),
        "conflictFreeAssignments": metrics.get("conflictFreeAssignments"),
        "executionValid": metrics.get("executionValid"),
        "robustUtilityAverage": metrics.get("robustUtilityAverage"),
        "routeCostQuality": metrics.get("routeCostQuality"),
        "driverEntryQuality": metrics.get("driverEntryQuality"),
        "workerFallbackRate": metrics.get("workerFallbackRate"),
        "stageFallbackCount": stage_summary.get("totalFallbacks", 0),
        "routeProposalCount": route_metrics.get("proposalCount"),
        "routeGeometryCoverage": route_metrics.get("geometryCoverage"),
        "llmRequestCount": token_usage.get("requestCount", 0),
        "llmTotalTokens": token_usage.get("totalTokens", 0),
        "stageLatencies": summarize_stage_latencies(result.decision_log),
        "mlInvocations": summarize_ml_invocations(result.decision_log),
        "routeProposalBudgetMetrics": route_budget_metrics,
        "workerStatusSnapshot": payload.get("workerStatusSnapshot", {}),
    }


def verdict_counts(rows: Iterable[Dict[str, object]]) -> Dict[str, int]:
    counts = {verdict: 0 for verdict in VERDICTS}
    for row in rows:
        verdict = str(row.get("verdict", "EVIDENCE_GAP"))
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def git_commit() -> str:
    completed = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if completed.returncode == 0 and completed.stdout.strip():
        return completed.stdout.strip()
    return "workspace"


def write_reports(rows: Sequence[Dict[str, object]], output_root: Path, matrix: str, provider_status: Dict[str, object]) -> Tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    payload = {
        "schemaVersion": "dispatch-v2-standard-comparison/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gitCommit": git_commit(),
        "matrix": matrix,
        "providerStatus": provider_status,
        "verdictCounts": verdict_counts(rows),
        "cells": list(rows),
    }
    json_path = output_root / f"standard_comparison-{timestamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report_path = output_root / "standard_comparison_report.md"
    report_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, report_path


def render_markdown(payload: Dict[str, object]) -> str:
    rows = payload.get("cells", [])
    counts = payload.get("verdictCounts", {})
    lines = [
        "# Dispatch V2 Standard Comparison",
        "",
        f"- schema: `{payload.get('schemaVersion')}`",
        f"- generated at: `{payload.get('generatedAt')}`",
        f"- git commit: `{payload.get('gitCommit')}`",
        f"- matrix: `{payload.get('matrix')}`",
        f"- provider ready: `{payload.get('providerStatus', {}).get('ready')}`",
        f"- verdict counts: `{counts}`",
        "",
        "## Cells",
        "",
        "| scenario | size | profile | verdict | latency ms | executed | robust utility | route proposals | fallbacks | llm requests |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            lines.append(
                "| {scenario} | {size} | {profile} | {verdict} | {latency} | {executed} | {utility} | {routes} | {fallbacks} | {llm} |".format(
                    scenario=row.get("scenarioPack", ""),
                    size=row.get("size", ""),
                    profile=row.get("profile", ""),
                    verdict=row.get("verdict", ""),
                    latency=row.get("totalLatencyMs") if row.get("totalLatencyMs") is not None else "",
                    executed=row.get("executedAssignmentCount") if row.get("executedAssignmentCount") is not None else "",
                    utility=row.get("robustUtilityAverage") if row.get("robustUtilityAverage") is not None else "",
                    routes=row.get("routeProposalCount") if row.get("routeProposalCount") is not None else "",
                    fallbacks=row.get("stageFallbackCount", 0),
                    llm=row.get("llmRequestCount", 0),
                )
            )
    lines.extend(["", "## Verdict Reasons", ""])
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                lines.append(f"- `{row.get('scenarioPack')}/{row.get('size')}/{row.get('profile')}`: `{row.get('verdict')}` {row.get('verdictReasons')}")
    lines.append("")
    return "\n".join(lines)


def print_plan(cells: Sequence[StandardCell]) -> None:
    print(f"[STANDARD COMPARISON MATRIX] {len(cells)} cell(s)")
    for cell in cells:
        spec = cell.profile
        print(
            f"- scenario={cell.scenario_pack} size={cell.size} profile={spec.name} baseline={spec.baseline} "
            f"decision-mode={spec.decision_mode} prompt-family={spec.prompt_family} runtime-profile={spec.profile or 'default'} "
            f"authoritative-stages={list(spec.authoritative_stages)} timeout={spec.timeout_seconds}s"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Dispatch V2 standard comparison benchmark matrix.")
    parser.add_argument("--matrix", choices=("local-minimum", "ml-only-4case", "llm-gated", "standard-v1"), default="local-minimum")
    parser.add_argument("--profiles", default="", help="Comma-separated logical profiles. Defaults depend on --matrix.")
    parser.add_argument("--scenarios", default="", help="Comma-separated scenario packs. Defaults depend on --matrix.")
    parser.add_argument("--size", default="", help="Comma-separated sizes. Defaults to S, or S,M for standard-v1.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-llm-preflight", action="store_true", help="Do not probe /responses before LLM cells.")
    args = parser.parse_args(argv)

    try:
        cells = planned_cells(args.matrix, args.scenarios, args.profiles, args.size)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 2
    print_plan(cells)
    if args.dry_run:
        return 0

    output_root = Path(args.output_root)
    has_llm_cells = any(cell.profile.requires_llm for cell in cells)
    provider_ready, provider_reason = (True, "not-required")
    if has_llm_cells:
        provider_ready, provider_reason = llm_preflight_ready(output_root, skip=args.skip_llm_preflight)
        print(f"[LLM PREFLIGHT] ready={str(provider_ready).lower()} reason={provider_reason}")

    results: List[CellRunResult] = []
    for cell in cells:
        print(f"[CELL STARTED] {cell.cell_id}")
        result = run_standard_cell(cell, output_root, provider_ready, provider_reason)
        results.append(result)
        print(f"[CELL COMPLETED] {cell.cell_id} verdict={result.verdict} reasons={list(result.verdict_reasons)}")

    rows = [cell_report_row(result) for result in results]
    json_path, report_path = write_reports(rows, output_root, args.matrix, {"ready": provider_ready, "reason": provider_reason})
    print(f"[STANDARD COMPARISON JSON] {json_path}")
    print(f"[STANDARD COMPARISON REPORT] {report_path}")
    return 1 if any(row["verdict"] == "FAIL" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
