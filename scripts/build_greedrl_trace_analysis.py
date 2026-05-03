from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload
    except (OSError, UnicodeDecodeError):
        return


def adaptive_trace_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.json") if "adaptive_compute_trace" in path.parts)


def teacher_trace_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.jsonl"))


def quality_artifact_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("dispatch-quality-*-legacy-v2-controlled-*.json"))


def analyze_adaptive(paths: list[Path]) -> dict[str, Any]:
    skip_reasons: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    escalated = 0
    skipped = 0
    rows = 0
    worker_ready_false = 0
    examples: list[dict[str, Any]] = []
    for path in paths:
        payload = read_json(path)
        if not payload or str(payload.get("workerName", "")).lower() != "ml-greedrl-worker":
            continue
        rows += 1
        decision = str(payload.get("decision", "unknown")) or "unknown"
        decisions[decision] += 1
        if not bool(payload.get("workerReady", True)):
            worker_ready_false += 1
        if bool(payload.get("escalated")):
            escalated += 1
        else:
            skipped += 1
            skip_reasons[str(payload.get("reason", "unknown")) or "unknown"] += 1
        if len(examples) < 8:
            examples.append({
                "file": str(path),
                "decision": decision,
                "escalated": bool(payload.get("escalated")),
                "reason": payload.get("reason", ""),
                "workingOrderCount": payload.get("workingOrderCount"),
                "acceptedBoundaryOrderCount": payload.get("acceptedBoundaryOrderCount"),
                "supportSpread": payload.get("supportSpread"),
                "workerReady": payload.get("workerReady"),
            })
    return {
        "adaptiveTraceRowCount": rows,
        "greedrlEscalatedCount": escalated,
        "greedrlSkippedCount": skipped,
        "workerReadyFalseCount": worker_ready_false,
        "decisionCounts": dict(sorted(decisions.items())),
        "skipReasons": dict(sorted(skip_reasons.items())),
        "examples": examples,
    }


def analyze_teacher(paths: list[Path]) -> dict[str, Any]:
    missing_reasons: Counter[str] = Counter()
    applied = 0
    fallback = 0
    rows = 0
    proposal_count = 0
    non_empty_proposal_rows = 0
    max_proposals = 0
    working_order_counts: list[int] = []
    examples: list[dict[str, Any]] = []
    for path in paths:
        for payload in read_jsonl(path):
            if str(payload.get("teacherFamily", "")).lower() != "greedrl":
                continue
            rows += 1
            applied += 1 if bool(payload.get("applied")) else 0
            fallback += 1 if bool(payload.get("fallbackUsed")) else 0
            reason = str(payload.get("missingReason") or payload.get("notAppliedReason") or "")
            if reason:
                missing_reasons[reason] += 1
            proposals = payload.get("bundleProposals") if isinstance(payload.get("bundleProposals"), list) else []
            proposal_count += len(proposals)
            max_proposals = max(max_proposals, len(proposals))
            if proposals:
                non_empty_proposal_rows += 1
            features = payload.get("featureVector") if isinstance(payload.get("featureVector"), dict) else {}
            working_order_ids = features.get("workingOrderIds") if isinstance(features.get("workingOrderIds"), list) else []
            working_order_counts.append(len(working_order_ids))
            if len(examples) < 8:
                examples.append({
                    "file": str(path),
                    "applied": bool(payload.get("applied")),
                    "fallbackUsed": bool(payload.get("fallbackUsed")),
                    "missingReason": reason,
                    "workingOrderCount": len(working_order_ids),
                    "proposalCount": len(proposals),
                })
    return {
        "teacherTraceRowCount": rows,
        "appliedRowCount": applied,
        "fallbackRowCount": fallback,
        "proposalCount": proposal_count,
        "nonEmptyProposalRowCount": non_empty_proposal_rows,
        "maxProposalsInRow": max_proposals,
        "averageWorkingOrderCount": round(sum(working_order_counts) / len(working_order_counts), 3) if working_order_counts else 0.0,
        "missingReasons": dict(sorted(missing_reasons.items())),
        "examples": examples,
    }


def analyze_quality(paths: list[Path]) -> dict[str, Any]:
    rows = 0
    greedrl_enabled = 0
    source_counts: Counter[str] = Counter()
    family_generated: Counter[str] = Counter()
    family_retained: Counter[str] = Counter()
    weak_pool_rows = 0
    dense_rows = 0
    for path in paths:
        payload = read_json(path)
        if not payload:
            continue
        rows += 1
        scenario = str(payload.get("scenarioPack", ""))
        if "dense" in scenario:
            dense_rows += 1
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        if bool(config.get("greedrlEnabled")):
            greedrl_enabled += 1
        bundle = payload.get("bundleDiversity") if isinstance(payload.get("bundleDiversity"), dict) else {}
        if int(bundle.get("familyDiversityCount", 0) or 0) <= 1:
            weak_pool_rows += 1
        for key, value in (bundle.get("sourceCounts") if isinstance(bundle.get("sourceCounts"), dict) else {}).items():
            source_counts[str(key)] += int(value or 0)
        for key, value in (bundle.get("familyGeneratedCounts") if isinstance(bundle.get("familyGeneratedCounts"), dict) else {}).items():
            family_generated[str(key)] += int(value or 0)
        for key, value in (bundle.get("familyRetainedCounts") if isinstance(bundle.get("familyRetainedCounts"), dict) else {}).items():
            family_retained[str(key)] += int(value or 0)
    return {
        "qualityArtifactRowCount": rows,
        "greedrlEnabledRowCount": greedrl_enabled,
        "denseScenarioRowCount": dense_rows,
        "weakBundlePoolRowCount": weak_pool_rows,
        "sourceCounts": dict(sorted(source_counts.items())),
        "familyGeneratedCounts": dict(sorted(family_generated.items())),
        "familyRetainedCounts": dict(sorted(family_retained.items())),
    }


def diagnose(adaptive: dict[str, Any], teacher: dict[str, Any], quality: dict[str, Any]) -> list[str]:
    diagnoses: list[str] = []
    if adaptive["adaptiveTraceRowCount"] and adaptive["greedrlEscalatedCount"] == 0:
        diagnoses.append("greedrl-never-escalated-by-adaptive-gate")
    if teacher["teacherTraceRowCount"] and teacher["proposalCount"] == 0:
        diagnoses.append("greedrl-teacher-generated-no-proposals")
    if teacher["missingReasons"].get("greedrl-scope-too-large", 0) > 0:
        diagnoses.append("greedrl-scope-too-large-present")
    if quality["qualityArtifactRowCount"] and quality["greedrlEnabledRowCount"] == 0:
        diagnoses.append("quality-benchmark-greedrl-disabled")
    if quality["weakBundlePoolRowCount"] > 0:
        diagnoses.append("weak-bundle-pool-opportunity-present")
    if not diagnoses:
        diagnoses.append("no-obvious-greedrl-bottleneck-detected")
    return diagnoses


def build_report(feedback_root: Path, teacher_root: Path, quality_root: Path) -> dict[str, Any]:
    adaptive = analyze_adaptive(adaptive_trace_paths(feedback_root))
    teacher = analyze_teacher(teacher_trace_paths(teacher_root))
    quality = analyze_quality(quality_artifact_paths(quality_root))
    return {
        "schemaVersion": "greedrl-trace-analysis/v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "feedbackRoot": str(feedback_root),
        "teacherRoot": str(teacher_root),
        "qualityRoot": str(quality_root),
        "adaptive": adaptive,
        "teacher": teacher,
        "quality": quality,
        "diagnoses": diagnose(adaptive, teacher, quality),
        "recommendedNextActions": recommended_actions(adaptive, teacher, quality),
    }


def recommended_actions(adaptive: dict[str, Any], teacher: dict[str, Any], quality: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if quality["greedrlEnabledRowCount"] == 0:
        actions.append("run-focused-dense-bundle-benchmark-with-greedrl-enabled")
    if adaptive["adaptiveTraceRowCount"] and adaptive["greedrlEscalatedCount"] == 0:
        actions.append("tune-adaptive-greedrl-gate-for-dense-or-weak-pool-cases")
    if teacher["teacherTraceRowCount"] and teacher["proposalCount"] == 0:
        actions.append("inspect-greedrl-worker-input-scope-and-max-orders-per-request")
    if teacher["proposalCount"] > 0 and not quality["sourceCounts"]:
        actions.append("add-bundle-source-count-telemetry-or-greedrl-retention-quota")
    if quality["weakBundlePoolRowCount"] > 0:
        actions.append("prioritize-greedrl-for-weak-bundle-pool-scenarios")
    if not actions:
        actions.append("keep-greedrl-gated-and-run-positive-contribution-ablation")
    return actions


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GreedRL Trace Analysis",
        "",
        f"- diagnoses: `{report['diagnoses']}`",
        f"- recommended actions: `{report['recommendedNextActions']}`",
        "",
        "## Adaptive Gate",
        "",
        f"- rows: `{report['adaptive']['adaptiveTraceRowCount']}`",
        f"- escalated: `{report['adaptive']['greedrlEscalatedCount']}`",
        f"- skipped: `{report['adaptive']['greedrlSkippedCount']}`",
        f"- skip reasons: `{report['adaptive']['skipReasons']}`",
        "",
        "## Teacher Trace",
        "",
        f"- rows: `{report['teacher']['teacherTraceRowCount']}`",
        f"- applied rows: `{report['teacher']['appliedRowCount']}`",
        f"- fallback rows: `{report['teacher']['fallbackRowCount']}`",
        f"- proposal count: `{report['teacher']['proposalCount']}`",
        f"- missing reasons: `{report['teacher']['missingReasons']}`",
        "",
        "## Quality Artifacts",
        "",
        f"- rows: `{report['quality']['qualityArtifactRowCount']}`",
        f"- GreedRL enabled rows: `{report['quality']['greedrlEnabledRowCount']}`",
        f"- dense rows: `{report['quality']['denseScenarioRowCount']}`",
        f"- weak pool rows: `{report['quality']['weakBundlePoolRowCount']}`",
        f"- family retained: `{report['quality']['familyRetainedCounts']}`",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze GreedRL gate, teacher, and quality traces.")
    parser.add_argument("--feedback-root", default="artifacts/benchmark")
    parser.add_argument("--teacher-root", default="data/bronze/greedrl-teacher-trace")
    parser.add_argument("--quality-root", default="artifacts/benchmark/stress-runtime")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    report = build_report(Path(args.feedback_root), Path(args.teacher_root), Path(args.quality_root))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "greedrl_trace_analysis.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "greedrl_trace_analysis.md").write_text(markdown(report), encoding="utf-8")
    print(f"[GREEDRL TRACE] wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
