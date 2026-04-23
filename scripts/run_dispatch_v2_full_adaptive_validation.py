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
    payload: dict


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


def case_cells(mode: str, decision_mode: str, prompt_family: str, profile: str) -> List[ValidationCell]:
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
        for scenario_pack, size in TARGET_CASES
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
            for scenario_pack, size in TARGET_CASES
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


def collect_benchmark_results(root: Path, root_type: str) -> Dict[Tuple[str, str, str, str, str], dict]:
    indexed: Dict[Tuple[str, str, str, str, str], dict] = {}
    if not root.exists():
        return indexed
    for path in sorted(root.rglob("dispatch-quality*.json")):
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
        payload["_rootPath"] = str(root)
        payload["_artifactPath"] = str(path)
        indexed[key] = payload
    return indexed


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
        payload=payload,
    )


def collect_adaptive_rows(root: Path, root_type: str) -> Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]]:
    indexed: Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]] = {}
    if not root.exists():
        return indexed
    for path in sorted(root.rglob("*.json")):
        row = parse_adaptive_trace(path, root_type, root)
        if row is None:
            continue
        key = (row.scenario_pack, row.size, row.execution_mode, row.decision_mode, row.prompt_family)
        indexed.setdefault(key, []).append(row)
    return indexed


def parse_instant(value: object) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
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
            "applied": worker.get("applied"),
            "notAppliedReason": worker.get("notAppliedReason", ""),
        }
        for worker in workers
    ]


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
        })
        worker_entry["totalDecisions"] += 1
        worker_entry["escalatedCount"] += 1 if row.escalated else 0
        worker_entry["skippedCount"] += 0 if row.escalated else 1
        worker_entry["reasons"][row.reason or "unspecified"] = worker_entry["reasons"].get(row.reason or "unspecified", 0) + 1
        if row.device_used:
            worker_entry["devicesUsed"].add(row.device_used)

        stage_entry = stage_summary.setdefault(row.stage_name or "unknown-stage", {
            "totalDecisions": 0,
            "escalatedCount": 0,
            "skippedCount": 0,
            "reasons": {},
        })
        stage_entry["totalDecisions"] += 1
        stage_entry["escalatedCount"] += 1 if row.escalated else 0
        stage_entry["skippedCount"] += 0 if row.escalated else 1
        stage_entry["reasons"][row.reason or "unspecified"] = stage_entry["reasons"].get(row.reason or "unspecified", 0) + 1

    for entry in worker_summary.values():
        entry["devicesUsed"] = sorted(entry["devicesUsed"])
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
    metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
    return {
        "artifactPath": result.get("_artifactPath", ""),
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
        "stageFallbackSummary": result.get("stageFallbackSummary", {}),
        "workerDeviceAudit": worker_device_audit(result),
    }


def determine_verdict(adaptive_summary: dict, comparison_summary: dict) -> Tuple[str, List[str]]:
    adaptive_benchmark = adaptive_summary.get("benchmark", {})
    adaptive_trace = adaptive_summary.get("adaptiveTrace", {})
    reasons: List[str] = []
    if not adaptive_benchmark:
        return "EVIDENCE_GAP", ["adaptive-benchmark-missing"]
    if not adaptive_trace or adaptive_trace.get("totalAdaptiveDecisions", 0) == 0:
        return "EVIDENCE_GAP", ["adaptive-trace-missing"]
    if adaptive_benchmark.get("mlAttachStatus") == "ML_ATTACH_FAIL":
        return "REGRESSION_RISK", ["ml-attach-failed"]
    if adaptive_benchmark.get("timeoutPhase") not in (None, "", "NONE"):
        return "REGRESSION_RISK", [f"timeout:{adaptive_benchmark.get('timeoutPhase')}"]
    if int(adaptive_benchmark.get("selectedProposalCount") or 0) <= 0:
        return "REGRESSION_RISK", ["selected-proposals-empty"]
    if int(adaptive_benchmark.get("executedAssignmentCount") or 0) <= 0:
        reasons.append("executed-assignments-empty")
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
) -> dict:
    key = (scenario_pack, size, "controlled", decision_mode, prompt_family)
    adaptive_result = adaptive_results.get(key)
    comparison_result = comparison_results.get(key)
    adaptive_rows = adaptive_traces.get(key, [])
    adaptive_summary = {
        "benchmark": benchmark_summary(adaptive_result),
        "adaptiveTrace": summarize_traces(adaptive_rows),
    }
    comparison_summary = benchmark_summary(comparison_result)
    verdict, reasons = determine_verdict(adaptive_summary, comparison_summary)
    return {
        "caseId": f"{scenario_pack}/{size}/controlled/{decision_mode}/{prompt_family}",
        "scenarioPack": scenario_pack,
        "workloadSize": size,
        "executionMode": "controlled",
        "decisionMode": decision_mode,
        "promptFamily": prompt_family,
        "adaptive": adaptive_summary,
        "comparison": comparison_summary,
        "verdict": verdict,
        "verdictReasons": reasons,
    }


def markdown_report(payload: dict) -> str:
    lines = [
        "# Full Adaptive Validation Report",
        "",
        f"- generatedAt: `{payload['generatedAt']}`",
        f"- validationCommit: `{payload['validationCommit']}`",
        f"- mode: `{payload['mode']}`",
        f"- decisionMode: `{payload['decisionMode']}`",
        f"- promptFamily: `{payload['promptFamily']}`",
        f"- adaptiveProfile: `{payload['adaptiveProfile']}`",
        f"- adaptiveRoots: `{', '.join(payload['adaptiveRoots']) or 'none'}`",
        f"- comparisonRoots: `{', '.join(payload['comparisonRoots']) or 'none'}`",
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
        lines.append(
            f"- adaptive trace: total=`{adaptive_trace.get('totalAdaptiveDecisions', 0)}` "
            f"skipped=`{adaptive_trace.get('skippedCount', 0)}` "
            f"escalated=`{adaptive_trace.get('escalatedCount', 0)}`"
        )
        comparison = case["comparison"]
        if comparison:
            lines.append(
                f"- comparison benchmark: latencyMs=`{comparison.get('latencyMs', 'n/a')}` "
                f"selected=`{comparison.get('selectedProposalCount', 'n/a')}` "
                f"executed=`{comparison.get('executedAssignmentCount', 'n/a')}` "
                f"robustUtility=`{comparison.get('robustUtilityAverage', 'n/a')}`"
            )
        for worker_name, summary in sorted(adaptive_trace.get("workers", {}).items()):
            lines.append(
                f"- worker `{worker_name}` decisions=`{summary['totalDecisions']}` "
                f"escalated=`{summary['escalatedCount']}` skipped=`{summary['skippedCount']}` "
                f"devices=`{summary['devicesUsed']}` reasons=`{summary['reasons']}`"
            )
        if adaptive_benchmark.get("workerDeviceAudit"):
            for worker in adaptive_benchmark["workerDeviceAudit"]:
                lines.append(
                    f"- device audit `{worker['workerName']}` enabled=`{worker['enabled']}` ready=`{worker['ready']}` "
                    f"device=`{worker['device']}` dtype=`{worker['dtype']}` "
                    f"gpuMemoryAllocatedMb=`{worker['gpuMemoryAllocatedMb']}` batchSize=`{worker['batchSize']}` "
                    f"compileMode=`{worker['compileMode']}` applied=`{worker['applied']}`"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(payload: dict, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"full_adaptive_validation-{timestamp}.json"
    markdown_path = output_dir / "full_adaptive_validation_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(payload), encoding="utf-8")
    return json_path, markdown_path


def collect_case_reports(
    adaptive_roots: Sequence[Path],
    comparison_roots: Sequence[Path],
    decision_mode: str,
    prompt_family: str,
) -> List[dict]:
    adaptive_results: Dict[Tuple[str, str, str, str, str], dict] = {}
    adaptive_trace_index: Dict[Tuple[str, str, str, str, str], List[AdaptiveTraceRow]] = {}
    comparison_results: Dict[Tuple[str, str, str, str, str], dict] = {}
    for root in adaptive_roots:
        adaptive_results.update(collect_benchmark_results(root, "adaptive"))
        for key, rows in collect_adaptive_rows(root, "adaptive").items():
            adaptive_trace_index.setdefault(key, []).extend(rows)
    for root in comparison_roots:
        comparison_results.update(collect_benchmark_results(root, "comparison"))
    return [
        build_case_report(scenario_pack, size, decision_mode, prompt_family, adaptive_results, comparison_results, adaptive_trace_index)
        for scenario_pack, size in TARGET_CASES
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 full-adaptive validation evidence rail.")
    parser.add_argument("--adaptive-root", action="append", default=[])
    parser.add_argument("--comparison-root", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--mode", choices=("adaptive-only", "paired"), default="paired")
    parser.add_argument("--decision-mode", choices=("legacy", "llm-shadow", "llm-authoritative"), default="llm-authoritative")
    parser.add_argument("--prompt-family", choices=("v2", "v3"), default="v2")
    parser.add_argument("--profile", default="dispatch-v2-full-adaptive")
    parser.add_argument("--rerun-cells", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    adaptive_roots = [Path(path) for path in args.adaptive_root]
    comparison_roots = [Path(path) for path in args.comparison_root]
    cells = case_cells(args.mode, args.decision_mode, args.prompt_family, args.profile)
    print(f"[FULL ADAPTIVE VALIDATION] case-count={len(cells)}")
    for cell in cells:
        print(
            f"- root-type={cell.root_type} scenario-pack={cell.scenario_pack} size={cell.size} "
            f"decision-mode={cell.decision_mode} prompt-family={cell.prompt_family} "
            f"execution-mode={cell.execution_mode} profile={cell.profile or 'default'}"
        )
    if args.dry_run:
        return 0

    rerun_executed = False
    if args.rerun_cells:
        rerun_executed = True
        for cell in cells:
            live_root = output_dir / "live" / ("full-adaptive" if cell.root_type == "adaptive" else "pre-adaptive")
            if cell.root_type == "adaptive":
                if live_root not in adaptive_roots:
                    adaptive_roots.append(live_root)
            else:
                if live_root not in comparison_roots:
                    comparison_roots.append(live_root)
            print(f"[CELL STARTED] root-type={cell.root_type} scenario-pack={cell.scenario_pack}")
            exit_code = run_validation_cell(cell, live_root)
            if exit_code != 0:
                print(f"[CELL FAILED] root-type={cell.root_type} scenario-pack={cell.scenario_pack} exit={exit_code}")
                return exit_code
            print(f"[CELL COMPLETED] root-type={cell.root_type} scenario-pack={cell.scenario_pack}")

    cases = collect_case_reports(adaptive_roots, comparison_roots, args.decision_mode, args.prompt_family)
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
