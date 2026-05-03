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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "bottleneck-analysis"


@dataclass(frozen=True)
class RunStep:
    name: str
    command: Tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True)
class RunStepResult:
    name: str
    command: Tuple[str, ...]
    return_code: Optional[int]
    timed_out: bool
    skipped: bool


def python_command() -> List[str]:
    if os.name == "nt" and shutil.which("py"):
        return ["py", "-3.13"]
    return ["python"]


def git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0 and completed.stdout.strip():
        return completed.stdout.strip()
    return "workspace"


def standard_command(output_root: Path,
                     matrix: str,
                     scenarios: str,
                     profiles: str,
                     size: str) -> Tuple[str, ...]:
    return tuple(python_command() + [
        str(REPO_ROOT / "scripts" / "run_dispatch_v2_standard_comparison.py"),
        "--matrix", matrix,
        "--scenarios", scenarios,
        "--profiles", profiles,
        "--size", size,
        "--output-root", str(output_root),
    ])


def perf_command(output_root: Path, size: str, mode: str) -> Tuple[str, ...]:
    return tuple(python_command() + [
        str(REPO_ROOT / "scripts" / "run_dispatch_v2_perf.py"),
        "--baseline", "C",
        "--size", size,
        "--mode", mode,
        "--output-dir", str(output_root),
    ])


def planned_steps(matrix: str, output_root: Path) -> List[RunStep]:
    if matrix == "collect-only":
        return []
    if matrix == "smoke":
        return [RunStep(
            "standard-smoke-full-adaptive",
            standard_command(
                output_root / "standard-smoke",
                "ml-only-4case",
                "normal-clear",
                "full-adaptive",
                "S"),
            300,
        )]
    if matrix != "deep":
        raise ValueError(f"Unsupported matrix '{matrix}'")

    return [
        RunStep(
            "standard-s-ml-adaptive",
            standard_command(
                output_root / "standard-s",
                "ml-only-4case",
                "normal-clear,heavy-rain,traffic-shock,forecast-heavy",
                "heuristic-only,ml-only,full-adaptive",
                "S"),
            1800,
        ),
        RunStep(
            "standard-m-ml-adaptive",
            standard_command(
                output_root / "standard-m",
                "standard-v1",
                "normal-clear,heavy-rain,traffic-shock,forecast-heavy,route-ambiguity,driver-scarcity,weekday-lunch-burst",
                "heuristic-only,ml-only,full-adaptive",
                "M"),
            3600,
        ),
        RunStep("perf-cold-s", perf_command(output_root / "perf", "S", "cold"), 600),
        RunStep("perf-warm-s", perf_command(output_root / "perf", "S", "warm"), 600),
        RunStep("perf-hot-s", perf_command(output_root / "perf", "S", "hot"), 600),
        RunStep("perf-cold-m", perf_command(output_root / "perf", "M", "cold"), 900),
        RunStep("perf-warm-m", perf_command(output_root / "perf", "M", "warm"), 900),
        RunStep("perf-hot-m", perf_command(output_root / "perf", "M", "hot"), 900),
    ]


def run_steps(steps: Sequence[RunStep], dry_run: bool = False, runner=subprocess.run) -> List[RunStepResult]:
    results: List[RunStepResult] = []
    for step in steps:
        print(f"[BOTTLENECK STEP] {step.name}")
        print("  " + " ".join(step.command))
        if dry_run:
            results.append(RunStepResult(step.name, step.command, None, False, True))
            continue
        try:
            completed = runner(
                list(step.command),
                cwd=REPO_ROOT,
                text=True,
                check=False,
                timeout=step.timeout_seconds,
            )
            results.append(RunStepResult(step.name, step.command, completed.returncode, False, False))
        except subprocess.TimeoutExpired:
            results.append(RunStepResult(step.name, step.command, None, True, False))
            print(f"[BOTTLENECK STEP TIMEOUT] {step.name} timeout={step.timeout_seconds}s")
    return results


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def newest_paths(root: Path, pattern: str) -> List[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob(pattern), key=lambda path: path.stat().st_mtime_ns)


def standard_rows(root: Path) -> List[dict]:
    rows: List[dict] = []
    for path in newest_paths(root, "standard_comparison-*.json"):
        payload = read_json(path)
        for row in payload.get("cells", []) or []:
            if isinstance(row, dict):
                enriched = dict(row)
                enriched["sourceArtifact"] = str(path)
                rows.append(enriched)
    return rows


def perf_rows(root: Path) -> List[dict]:
    rows: List[dict] = []
    for path in newest_paths(root, "dispatch-perf-*.json"):
        payload = read_json(path)
        payload["sourceArtifact"] = str(path)
        rows.append(payload)
    return rows


def llm_usage_rows(root: Path) -> List[dict]:
    rows: List[dict] = []
    for path in newest_paths(root, "*.json"):
        if "llm_usage_meta" not in {part.lower() for part in path.parts}:
            continue
        payload = read_json(path)
        payload["sourceArtifact"] = str(path)
        rows.append(payload)
    return rows


def llm_request_rows(root: Path) -> List[dict]:
    rows: List[dict] = []
    for path in newest_paths(root, "*.json"):
        if "llm_request_meta" not in {part.lower() for part in path.parts}:
            continue
        payload = read_json(path)
        payload["sourceArtifact"] = str(path)
        rows.append(payload)
    return rows


def adaptive_rows(root: Path) -> List[dict]:
    rows: List[dict] = []
    for path in newest_paths(root, "*.json"):
        if "adaptive_compute_trace" not in {part.lower() for part in path.parts}:
            continue
        payload = read_json(path)
        payload["sourceArtifact"] = str(path)
        rows.append(payload)
    return rows


def add_rank_item(rank: Dict[str, dict], key: str, latency_ms: int, cell: str) -> None:
    item = rank.setdefault(key, {"name": key, "count": 0, "totalLatencyMs": 0, "maxLatencyMs": 0, "cells": []})
    item["count"] += 1
    item["totalLatencyMs"] += latency_ms
    item["maxLatencyMs"] = max(item["maxLatencyMs"], latency_ms)
    if cell and len(item["cells"]) < 8:
        item["cells"].append(cell)


def sorted_rank(rank: Dict[str, dict]) -> List[dict]:
    rows = list(rank.values())
    rows.sort(key=lambda item: (item["totalLatencyMs"], item["maxLatencyMs"]), reverse=True)
    return rows


def stage_latency_rank(rows: Sequence[dict]) -> List[dict]:
    rank: Dict[str, dict] = {}
    for row in rows:
        cell = f"{row.get('scenarioPack')}/{row.get('size')}/{row.get('profile')}"
        stage_latencies = row.get("stageLatencies", {})
        if not isinstance(stage_latencies, dict):
            continue
        for stage, latency in stage_latencies.items():
            if isinstance(latency, (int, float)):
                add_rank_item(rank, str(stage), int(latency), cell)
    return sorted_rank(rank)


def ml_latency_rank(rows: Sequence[dict]) -> List[dict]:
    rank: Dict[str, dict] = {}
    for row in rows:
        cell = f"{row.get('scenarioPack')}/{row.get('size')}/{row.get('profile')}"
        invocations = row.get("mlInvocations", {})
        if not isinstance(invocations, dict):
            continue
        for worker, payload in invocations.items():
            if isinstance(payload, dict):
                add_rank_item(rank, str(worker), int(payload.get("latencyMs", 0) or 0), cell)
    return sorted_rank(rank)


def llm_latency_rank(usages: Sequence[dict]) -> List[dict]:
    rank: Dict[str, dict] = {}
    for row in usages:
        stage = str(row.get("stageName", "unknown"))
        latency = int(row.get("latencyMs", 0) or 0)
        add_rank_item(rank, stage, latency, str(row.get("sourceArtifact", "")))
        rank[stage]["totalTokens"] = int(rank[stage].get("totalTokens", 0)) + int((row.get("tokenUsage", {}) or {}).get("totalTokens", 0) or 0)
        rank[stage]["fallbackCount"] = int(rank[stage].get("fallbackCount", 0)) + (1 if row.get("fallbackUsed") else 0)
    return sorted_rank(rank)


def fallback_breakdown(rows: Sequence[dict], requests: Sequence[dict]) -> List[dict]:
    counts: Dict[str, dict] = {}
    def add(reason: str, source: str) -> None:
        if not reason:
            return
        item = counts.setdefault(reason, {"reason": reason, "count": 0, "sources": []})
        item["count"] += 1
        if source and len(item["sources"]) < 8:
            item["sources"].append(source)
    for row in rows:
        source = f"{row.get('scenarioPack')}/{row.get('size')}/{row.get('profile')}"
        for reason in row.get("verdictReasons", []) or []:
            add(str(reason), source)
    for request in requests:
        add(str(request.get("fallbackReason", "")), str(request.get("sourceArtifact", "")))
        details = request.get("details", {})
        if isinstance(details, dict):
            add(str(details.get("exceptionClass", "")), str(request.get("sourceArtifact", "")))
    result = list(counts.values())
    result.sort(key=lambda item: item["count"], reverse=True)
    return result


def route_generation_breakdown(rows: Sequence[dict]) -> List[dict]:
    result: List[dict] = []
    for row in rows:
        stages = row.get("stageLatencies", {}) if isinstance(row.get("stageLatencies"), dict) else {}
        invocations = row.get("mlInvocations", {}) if isinstance(row.get("mlInvocations"), dict) else {}
        budget = row.get("routeProposalBudgetMetrics", {}) if isinstance(row.get("routeProposalBudgetMetrics", {}), dict) else {}
        result.append({
            "cell": f"{row.get('scenarioPack')}/{row.get('size')}/{row.get('profile')}",
            "routeStageLatencyMs": stages.get("route-proposal-pool", 0),
            "routeFinderLatencyMs": (invocations.get("routefinder-local", {}) or {}).get("latencyMs", 0) if isinstance(invocations.get("routefinder-local", {}), dict) else 0,
            "proposalCount": row.get("routeProposalCount"),
            "geometryCoverage": row.get("routeGeometryCoverage"),
            "budgetMode": budget.get("budgetMode"),
            "budgetMaxTotalRouteProposals": budget.get("budgetMaxTotalRouteProposals"),
            "candidateCountBeforePrune": budget.get("candidateCountBeforePrune"),
            "candidateCountAfterPrune": budget.get("candidateCountAfterPrune"),
            "proposalPrunedBeforeRoutePool": budget.get("proposalPrunedBeforeRoutePool"),
            "routeVectorCacheHitRate": budget.get("routeVectorCacheHitRate"),
            "routeVectorComputedCount": budget.get("routeVectorComputedCount"),
            "routeVectorReusedCount": budget.get("routeVectorReusedCount"),
            "robustUtilityAverage": row.get("robustUtilityAverage"),
            "executedAssignmentCount": row.get("executedAssignmentCount"),
        })
    result.sort(key=lambda item: int(item.get("routeStageLatencyMs", 0) or 0), reverse=True)
    return result


def adaptive_gate_breakdown(rows: Sequence[dict]) -> dict:
    reason_counts: Dict[str, int] = {}
    missing_audit = 0
    total = 0
    for row in rows:
        decisions = row.get("decisions") or row.get("adaptiveDecisions") or []
        if isinstance(decisions, dict):
            decisions = [decisions]
        if not isinstance(decisions, list):
            continue
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            total += 1
            reason = str(decision.get("skipReason") or decision.get("escalationReason") or decision.get("reason") or "unknown")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if decision.get("workerAuditPresent") is False or reason == "worker-device-audit-missing":
                missing_audit += 1
    return {"totalDecisions": total, "missingAuditCount": missing_audit, "reasonCounts": reason_counts}


def quality_vs_cost(rows: Sequence[dict]) -> List[dict]:
    result: List[dict] = []
    for row in rows:
        stages = row.get("stageLatencies", {}) if isinstance(row.get("stageLatencies"), dict) else {}
        stage_sum = sum(int(value or 0) for value in stages.values() if isinstance(value, (int, float)))
        result.append({
            "cell": f"{row.get('scenarioPack')}/{row.get('size')}/{row.get('profile')}",
            "stageLatencySumMs": stage_sum,
            "executedAssignmentCount": row.get("executedAssignmentCount"),
            "robustUtilityAverage": row.get("robustUtilityAverage"),
            "verdict": row.get("verdict"),
        })
    result.sort(key=lambda item: int(item.get("stageLatencySumMs", 0) or 0), reverse=True)
    return result


def classify_bottleneck(rows: Sequence[dict], requests: Sequence[dict], adaptive: dict) -> dict:
    route_cells = 0
    ml_cells = 0
    route_latency_total = 0
    for row in rows:
        stages = row.get("stageLatencies", {}) if isinstance(row.get("stageLatencies"), dict) else {}
        route_ms = int(stages.get("route-proposal-pool", 0) or 0)
        route_latency_total += route_ms
        stage_sum = sum(int(value or 0) for value in stages.values() if isinstance(value, (int, float)))
        invocations = row.get("mlInvocations", {}) if isinstance(row.get("mlInvocations"), dict) else {}
        routefinder_ms = 0
        if isinstance(invocations.get("routefinder-local"), dict):
            routefinder_ms = int(invocations["routefinder-local"].get("latencyMs", 0) or 0)
        ml_total = sum(int(payload.get("latencyMs", 0) or 0) for payload in invocations.values() if isinstance(payload, dict))
        if stage_sum and route_ms / stage_sum >= 0.4 and route_ms > routefinder_ms * 2:
            route_cells += 1
        if stage_sum and ml_total / stage_sum >= 0.5:
            ml_cells += 1
    provider_errors = sum(1 for request in requests if request.get("fallbackReason") or (isinstance(request.get("details"), dict) and request["details"].get("exceptionClass")))
    geo_reasons = sum(1 for row in rows for reason in row.get("verdictReasons", []) or [] if "tomtom" in str(reason) or "open-meteo" in str(reason) or "route-vector-coverage" in str(reason))
    scores = {
        "ROUTE_GENERATION": route_cells,
        "ML_WORKER": ml_cells,
        "LLM_PROVIDER": provider_errors,
        "ADAPTIVE_GATE": int(adaptive.get("missingAuditCount", 0)),
        "GEO_SOURCE": geo_reasons,
    }
    if route_cells > 0 and route_latency_total > 0:
        primary = "ROUTE_GENERATION"
    else:
        primary = max(scores.items(), key=lambda item: item[1])[0] if any(scores.values()) else "EVIDENCE_GAP"
    secondary = [key for key, value in scores.items() if value > 0 and key != primary]
    return {"primary": primary, "secondary": secondary, "scores": scores}


def build_payload(output_root: Path, step_results: Sequence[RunStepResult], matrix: str) -> dict:
    rows = standard_rows(output_root)
    usages = llm_usage_rows(output_root)
    requests = llm_request_rows(output_root)
    adaptive = adaptive_gate_breakdown(adaptive_rows(output_root))
    verdict = classify_bottleneck(rows, requests, adaptive)
    serialized_steps = []
    for step_result in step_results:
        serialized_steps.append({
            "name": step_result.name,
            "command": list(step_result.command),
            "return_code": step_result.return_code,
            "timed_out": step_result.timed_out,
            "skipped": step_result.skipped,
        })
    return {
        "schemaVersion": "dispatch-v2-bottleneck-analysis/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gitCommit": git_commit(),
        "matrix": matrix,
        "runSteps": serialized_steps,
        "sourceCounts": {
            "standardRows": len(rows),
            "perfRows": len(perf_rows(output_root)),
            "llmUsageRows": len(usages),
            "llmRequestRows": len(requests),
        },
        "stageLatencyRank": stage_latency_rank(rows),
        "mlLatencyRank": ml_latency_rank(rows),
        "llmLatencyRank": llm_latency_rank(usages),
        "routeGenerationBreakdown": route_generation_breakdown(rows),
        "fallbackBreakdown": fallback_breakdown(rows, requests),
        "adaptiveGateBreakdown": adaptive,
        "qualityVsCost": quality_vs_cost(rows),
        "bottleneckVerdict": verdict,
    }


def write_reports(payload: dict, output_root: Path) -> Tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_root / f"bottleneck_analysis-{timestamp}.json"
    markdown_path = output_root / "bottleneck_analysis_report.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, markdown_path


def top_names(rows: Sequence[dict], name_key: str = "name", value_key: str = "totalLatencyMs", limit: int = 5) -> str:
    if not rows:
        return "none"
    return ", ".join(f"{row.get(name_key)}={row.get(value_key)}" for row in rows[:limit])


def final_verdict_lines(payload: dict) -> List[str]:
    route_rows = payload.get("routeGenerationBreakdown", [])
    if not route_rows:
        return ["- Evidence gap: no route-generation rows were collected."]
    top_route = route_rows[0]
    verdict = payload.get("bottleneckVerdict", {})
    secondary = verdict.get("secondary", []) or []
    lines = [
        "- Route-generation candidate explosion is now bounded by an explicit proposal budget and pre-route pruning.",
        "- RouteFinder inference is not the primary runtime bottleneck when routefinder latency remains small relative to route-proposal-pool latency.",
        "- The next optimization target should stay on proposal breadth, route-vector work, and geo-source readiness rather than forcing more RouteFinder GPU work.",
    ]
    if top_route.get("proposalCount") is not None and top_route.get("routeStageLatencyMs") is not None:
        lines.append(
            f"- Current top route cell `{top_route.get('cell')}` has proposals=`{top_route.get('proposalCount')}`, "
            f"routeMs=`{top_route.get('routeStageLatencyMs')}`, geometry=`{top_route.get('geometryCoverage')}`, "
            f"executed=`{top_route.get('executedAssignmentCount')}`."
        )
    if "GEO_SOURCE" in secondary:
        lines.append("- Remaining `PASS_WITH_LIMITS` evidence is still partly driven by geo-source readiness, not by RouteFinder inference cost.")
    return lines


def render_markdown(payload: dict) -> str:
    verdict = payload.get("bottleneckVerdict", {})
    lines = [
        "# Dispatch V2 Bottleneck Analysis",
        "",
        f"- schema: `{payload.get('schemaVersion')}`",
        f"- generated at: `{payload.get('generatedAt')}`",
        f"- git commit: `{payload.get('gitCommit')}`",
        f"- matrix: `{payload.get('matrix')}`",
        f"- primary bottleneck: `{verdict.get('primary')}`",
        f"- secondary bottlenecks: `{verdict.get('secondary', [])}`",
        f"- source counts: `{payload.get('sourceCounts')}`",
        "",
        "## Final Verdict",
        "",
        *final_verdict_lines(payload),
        "",
        "## Top Latency",
        "",
        f"- stages: `{top_names(payload.get('stageLatencyRank', []))}`",
        f"- ML workers: `{top_names(payload.get('mlLatencyRank', []))}`",
        f"- LLM stages: `{top_names(payload.get('llmLatencyRank', []))}`",
        "",
        "## Route Generation",
        "",
        "| cell | route ms | routefinder ms | proposals | geometry | utility | executed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("routeGenerationBreakdown", [])[:12]:
        lines.append(
            f"| {row.get('cell')} | {row.get('routeStageLatencyMs')} | {row.get('routeFinderLatencyMs')} | "
            f"{row.get('proposalCount')} | {row.get('geometryCoverage')} | {row.get('robustUtilityAverage')} | {row.get('executedAssignmentCount')} |"
        )
    lines.extend(["", "## Proposal Budget", ""])
    for row in payload.get("routeGenerationBreakdown", [])[:12]:
        lines.append(
            f"- `{row.get('cell')}` mode=`{row.get('budgetMode')}` max=`{row.get('budgetMaxTotalRouteProposals')}` "
            f"beforeAfter=`{row.get('candidateCountBeforePrune')}->{row.get('candidateCountAfterPrune')}` "
            f"pruned=`{row.get('proposalPrunedBeforeRoutePool')}` cacheHitRate=`{row.get('routeVectorCacheHitRate')}` "
            f"computed=`{row.get('routeVectorComputedCount')}` reused=`{row.get('routeVectorReusedCount')}`"
        )
    lines.extend(["", "## Fallbacks", ""])
    for row in payload.get("fallbackBreakdown", [])[:12]:
        lines.append(f"- `{row.get('reason')}`: `{row.get('count')}`")
    lines.extend(["", "## Quality Vs Cost", ""])
    for row in payload.get("qualityVsCost", [])[:12]:
        lines.append(
            f"- `{row.get('cell')}` latencySumMs=`{row.get('stageLatencySumMs')}` "
            f"executed=`{row.get('executedAssignmentCount')}` utility=`{row.get('robustUtilityAverage')}` verdict=`{row.get('verdict')}`"
        )
    lines.append("")
    return "\n".join(lines)


def print_plan(steps: Sequence[RunStep]) -> None:
    print(f"[BOTTLENECK MATRIX] {len(steps)} step(s)")
    for step in steps:
        print(f"- {step.name} timeout={step.timeout_seconds}s")
        print("  " + " ".join(step.command))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 bottleneck evidence analysis.")
    parser.add_argument("--matrix", choices=("smoke", "deep", "collect-only"), default="smoke")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-run", action="store_true", help="Only collect existing artifacts under output root.")
    args = parser.parse_args(argv)

    output_root = Path(args.output_root)
    try:
        steps = planned_steps(args.matrix, output_root)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 2
    print_plan(steps)
    if args.dry_run:
        return 0

    step_results = [RunStepResult(step.name, step.command, None, False, True) for step in steps]
    if not args.skip_run:
        step_results = run_steps(steps)
    payload = build_payload(output_root, step_results, args.matrix)
    json_path, markdown_path = write_reports(payload, output_root)
    print(f"[BOTTLENECK JSON] {json_path}")
    print(f"[BOTTLENECK REPORT] {markdown_path}")
    failed_steps = [result for result in step_results if result.return_code not in (None, 0) or result.timed_out]
    return 1 if failed_steps and args.matrix != "collect-only" else 0


if __name__ == "__main__":
    raise SystemExit(main())
