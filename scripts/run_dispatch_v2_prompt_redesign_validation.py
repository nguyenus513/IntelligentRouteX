from __future__ import annotations

import argparse
import json
import subprocess
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "phase2-live3"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "prompt-redesign"
TARGET_STAGES = (
    "pair-bundle",
    "route-generation",
    "route-critique",
    "scenario",
    "final-selection",
)
STAGE_DEFAULTS = {
    "pair-bundle": {"scenario_pack": "normal-clear", "size": "S", "baseline": "C", "decision_mode": "llm-shadow", "execution_mode": "controlled"},
    "route-generation": {"scenario_pack": "heavy-rain", "size": "S", "baseline": "C", "decision_mode": "llm-shadow", "execution_mode": "controlled"},
    "route-critique": {"scenario_pack": "traffic-shock", "size": "S", "baseline": "C", "decision_mode": "llm-shadow", "execution_mode": "controlled"},
    "scenario": {"scenario_pack": "forecast-heavy", "size": "S", "baseline": "C", "decision_mode": "llm-shadow", "execution_mode": "controlled"},
    "final-selection": {"scenario_pack": "normal-clear", "size": "S", "baseline": "C", "decision_mode": "llm-shadow", "execution_mode": "controlled"},
}
EXPECTED_ASSESSMENT_FIELDS = (
    "id",
    "score",
    "rank",
    "selected",
    "confidence",
    "reasonCodes",
    "dominanceReasonCodes",
    "regretToBestAlternative",
    "driverFitSummary",
    "routeVectorRefs",
    "geospatialFlags",
    "burstSensitivityFlags",
    "rationale",
)
PROMPT_METADATA_FIELDS = (
    "promptSpecVersion",
    "stagePromptName",
    "stagePromptChecksum",
    "packetTemplateVersion",
    "packetTemplateChecksum",
    "candidateCountSeen",
    "comparisonPackCoverage",
    "geospatialCoverage",
    "missingContextFlags",
    "visibilityProfile",
    "comparisonLens",
    "geospatialLens",
    "fallbackReason",
)


@dataclass(frozen=True)
class ValidationCell:
    stage: str
    scenario_pack: str
    size: str
    baseline: str
    decision_mode: str
    execution_mode: str


@dataclass(frozen=True)
class StageFeedback:
    root_type: str
    root_path: str
    scenario_pack: str
    size: str
    execution_mode: str
    decision_mode: str
    authority_phase: str
    trace_id: str
    stage: str
    families: dict[str, dict]


def stage_cli_choices() -> list[str]:
    return list(TARGET_STAGES)


def benchmark_command() -> list[str]:
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


def normalize_stage_name(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text.lower().replace("_", "-") if text else ""


def remove_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if prefix and value.startswith(prefix) else value


def parse_stage_feedback(path: Path, root_type: str, root_path: Path) -> StageFeedback | None:
    parts = path.parts
    try:
        feedback_index = parts.index("feedback")
        decision_stage_index = parts.index("decision-stage")
    except ValueError:
        return None
    if decision_stage_index - feedback_index < 6:
        return None
    payload = json_read(path)
    trace_id = str(payload.get("traceId", "")).strip()
    stage = normalize_stage_name(payload.get("stageName") or remove_prefix(path.stem, trace_id + "-"))
    if not trace_id or not stage:
        return None
    return StageFeedback(
        root_type=root_type,
        root_path=str(root_path),
        scenario_pack=parts[feedback_index + 1],
        size=parts[feedback_index + 2].upper(),
        execution_mode=parts[feedback_index + 3],
        decision_mode=parts[feedback_index + 4],
        authority_phase=parts[feedback_index + 5],
        trace_id=trace_id,
        stage=stage,
        families={parts[decision_stage_index + 1]: payload},
    )


def merge_feedback_rows(rows: Iterable[StageFeedback]) -> dict[tuple[str, str, str, str, str, str, str, str], StageFeedback]:
    merged: dict[tuple[str, str, str, str, str, str, str, str], StageFeedback] = {}
    for row in rows:
        key = (
            row.root_type,
            row.root_path,
            row.scenario_pack,
            row.size,
            row.execution_mode,
            row.decision_mode,
            row.authority_phase,
            row.stage,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
        else:
            families = dict(existing.families)
            families.update(row.families)
            merged[key] = StageFeedback(
                root_type=existing.root_type,
                root_path=existing.root_path,
                scenario_pack=existing.scenario_pack,
                size=existing.size,
                execution_mode=existing.execution_mode,
                decision_mode=existing.decision_mode,
                authority_phase=existing.authority_phase,
                trace_id=existing.trace_id,
                stage=existing.stage,
                families=families,
            )
    return merged


def collect_feedback_rows(root: Path, root_type: str) -> list[StageFeedback]:
    feedback_root = root / "feedback"
    if not feedback_root.exists():
        return []
    rows = [parsed for path in feedback_root.rglob("*.json") if (parsed := parse_stage_feedback(path, root_type, root)) is not None]
    return list(merge_feedback_rows(rows).values())


def collect_benchmark_results(root: Path, root_type: str) -> list[dict]:
    if not root.exists():
        return []
    results: list[dict] = []
    for path in sorted(root.rglob("dispatch-quality*.json")):
        payload = json_read(path)
        if "baselineId" not in payload:
            continue
        payload["_rootType"] = root_type
        payload["_rootPath"] = str(root)
        payload["_artifactPath"] = str(path)
        results.append(payload)
    return results


def flatten_assessment_items(assessments: object) -> list[dict]:
    if not isinstance(assessments, dict):
        return []
    if isinstance(assessments.get("items"), list):
        return [item for item in assessments["items"] if isinstance(item, dict)]
    items: list[dict] = []
    for value in assessments.values():
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            items.extend(item for item in value["items"] if isinstance(item, dict))
    return items


def count_selected_and_non_selected(items: list[dict], join_payload: dict | None) -> tuple[int, int, bool]:
    selected_count = sum(1 for item in items if bool(item.get("selected")))
    non_selected_count = sum(1 for item in items if "selected" in item and not bool(item.get("selected")))
    if selected_count > 0 and non_selected_count > 0:
        return selected_count, non_selected_count, True
    join_payload = join_payload or {}
    selected_join = len(join_payload.get("selectedIds", [])) if isinstance(join_payload.get("selectedIds"), list) else 0
    rejected_join = len(join_payload.get("rejectedIds", [])) if isinstance(join_payload.get("rejectedIds"), list) else 0
    selected_count = max(selected_count, selected_join)
    non_selected_count = max(non_selected_count, rejected_join)
    return selected_count, non_selected_count, selected_count > 0 and non_selected_count > 0


def stage_output_payload(feedback: StageFeedback) -> dict:
    return feedback.families.get("decision_stage_output", {})


def stage_join_payload(feedback: StageFeedback) -> dict:
    return feedback.families.get("decision_stage_join", {})


def prompt_payload(feedback: StageFeedback) -> dict:
    if "llm_prompt_spec_trace" in feedback.families:
        return feedback.families["llm_prompt_spec_trace"]
    if "llm_request_meta" in feedback.families:
        return feedback.families["llm_request_meta"]
    return {}


def prompt_metadata_summary(feedback: StageFeedback) -> dict:
    prompt = prompt_payload(feedback)
    return {field: prompt.get(field) for field in PROMPT_METADATA_FIELDS if field in prompt}


def prompt_identity_locked(metadata: dict) -> bool:
    return (
        bool(metadata)
        and metadata.get("promptSpecVersion") not in (None, "", "generic-fallback/v1")
        and metadata.get("stagePromptChecksum") not in (None, "")
        and metadata.get("packetTemplateChecksum") not in (None, "")
    )


def context_verdict(metadata: dict) -> tuple[str, list[str]]:
    if not metadata:
        return "EVIDENCE_GAP", ["prompt-metadata-missing"]
    flags = [str(flag) for flag in metadata.get("missingContextFlags", [])] if isinstance(metadata.get("missingContextFlags"), list) else []
    candidate_count = int(metadata.get("candidateCountSeen", 0) or 0)
    comparison = metadata.get("comparisonPackCoverage")
    geospatial = metadata.get("geospatialCoverage")
    if candidate_count <= 0:
        return "FAIL", flags + ["candidate-count-empty"]
    if comparison is None or geospatial is None:
        return "EVIDENCE_GAP", flags + ["coverage-metadata-missing"]
    comparison_value = float(comparison)
    geospatial_value = float(geospatial)
    if comparison_value <= 0.0 or geospatial_value <= 0.0:
        return "FAIL", flags + ["coverage-zero"]
    if comparison_value < 1.0 or geospatial_value < 1.0 or flags:
        return "PASS_WITH_LIMITS", flags
    return "PASS", flags


def assessment_richness(items: list[dict]) -> float | None:
    if not items:
        return None
    total = 0.0
    for item in items:
        present = sum(1 for field in EXPECTED_ASSESSMENT_FIELDS if field in item)
        total += present / len(EXPECTED_ASSESSMENT_FIELDS)
    return total / len(items)


def assessment_verdict(items: list[dict], join_payload: dict | None) -> tuple[str, dict]:
    richness = assessment_richness(items)
    selected_count, non_selected_count, has_balance = count_selected_and_non_selected(items, join_payload)
    if richness is None:
        return "EVIDENCE_GAP", {
            "itemCount": 0,
            "richnessScore": None,
            "selectedCount": selected_count,
            "nonSelectedCount": non_selected_count,
            "selectedNonSelectedEvidencePresent": has_balance,
        }
    verdict = "PASS" if richness >= 0.75 and has_balance else "PASS_WITH_LIMITS" if richness >= 0.30 else "FAIL"
    return verdict, {
        "itemCount": len(items),
        "richnessScore": round(richness, 4),
        "selectedCount": selected_count,
        "nonSelectedCount": non_selected_count,
        "selectedNonSelectedEvidencePresent": has_balance,
    }


def fallback_verdict(output_payload: dict, prompt_meta: dict) -> tuple[str, dict]:
    meta = output_payload.get("meta") if isinstance(output_payload.get("meta"), dict) else {}
    fallback_used = bool(meta.get("fallbackUsed")) or bool(prompt_meta.get("fallbackReason"))
    fallback_reason = meta.get("fallbackReason") or prompt_meta.get("fallbackReason") or ""
    if fallback_used:
        return "FAIL", {"fallbackUsed": True, "fallbackReason": fallback_reason, "brainType": output_payload.get("brainType")}
    if not output_payload:
        return "EVIDENCE_GAP", {"fallbackUsed": None, "fallbackReason": "", "brainType": output_payload.get("brainType")}
    return "PASS", {"fallbackUsed": False, "fallbackReason": "", "brainType": output_payload.get("brainType")}


def overall_stage_verdict(prompt_locked: bool, context_status: str, fallback_status: str, assessment_status: str) -> str:
    if not prompt_locked:
        return "EVIDENCE_GAP"
    statuses = [context_status, fallback_status, assessment_status]
    if "FAIL" in statuses:
        return "FAIL"
    if "EVIDENCE_GAP" in statuses:
        return "EVIDENCE_GAP"
    if "PASS_WITH_LIMITS" in statuses:
        return "PASS_WITH_LIMITS"
    return "PASS"


def build_stage_evidence(feedback: StageFeedback, benchmark_result: dict | None) -> dict:
    prompt_meta = prompt_metadata_summary(feedback)
    output_payload = stage_output_payload(feedback)
    join_payload = stage_join_payload(feedback)
    items = flatten_assessment_items(output_payload.get("assessments"))
    context_status, context_flags = context_verdict(prompt_meta)
    assessment_status, assessment_summary = assessment_verdict(items, join_payload)
    fallback_status, fallback_summary = fallback_verdict(output_payload, prompt_meta)
    prompt_locked = prompt_identity_locked(prompt_meta)
    overall = overall_stage_verdict(prompt_locked, context_status, fallback_status, assessment_status)
    benchmark_summary = {}
    if benchmark_result is not None:
        benchmark_summary = {
            "artifactPath": benchmark_result.get("_artifactPath", ""),
            "baselineId": benchmark_result.get("baselineId"),
            "scenarioPack": benchmark_result.get("scenarioPack"),
            "workloadSize": benchmark_result.get("workloadSize"),
            "decisionMode": benchmark_result.get("decisionMode"),
            "executionMode": benchmark_result.get("executionMode"),
            "runAuthorityClass": benchmark_result.get("runAuthorityClass"),
            "authorityEligible": benchmark_result.get("authorityEligible"),
            "tokenUsageSummary": benchmark_result.get("tokenUsageSummary", {}),
            "stageFallbackSummary": benchmark_result.get("stageFallbackSummary", {}),
        }
    return {
        "rootType": feedback.root_type,
        "rootPath": feedback.root_path,
        "traceId": feedback.trace_id,
        "stageName": feedback.stage,
        "scenarioPack": feedback.scenario_pack,
        "workloadSize": feedback.size,
        "decisionMode": feedback.decision_mode,
        "executionMode": feedback.execution_mode,
        "authorityPhase": feedback.authority_phase,
        "promptIdentityLocked": prompt_locked,
        "promptMetadata": prompt_meta,
        "contextCoverageStatus": context_status,
        "missingContextFlags": sorted(set(context_flags)),
        "fallbackStatus": fallback_status,
        "fallbackSummary": fallback_summary,
        "assessmentRichnessStatus": assessment_status,
        "assessmentSummary": assessment_summary,
        "benchmarkSummary": benchmark_summary,
        "overallStageVerdict": overall,
    }


def build_stage_report(stage: str, baseline_evidence: list[dict], validation_evidence: list[dict]) -> dict:
    if validation_evidence:
        keys = {
            (
                entry.get("scenarioPack"),
                entry.get("workloadSize"),
                entry.get("decisionMode"),
                entry.get("executionMode"),
            )
            for entry in validation_evidence
        }
        baseline_evidence = [
            entry for entry in baseline_evidence
            if (
                entry.get("scenarioPack"),
                entry.get("workloadSize"),
                entry.get("decisionMode"),
                entry.get("executionMode"),
            ) in keys
        ]
    else:
        stage_default = STAGE_DEFAULTS[stage]
        baseline_evidence = [
            entry for entry in baseline_evidence
            if entry.get("scenarioPack") == stage_default["scenario_pack"]
            and entry.get("workloadSize") == stage_default["size"]
            and entry.get("decisionMode") == stage_default["decision_mode"]
            and entry.get("executionMode") == stage_default["execution_mode"]
        ]
    prompt_identity = {}
    for evidence in validation_evidence:
        metadata = evidence.get("promptMetadata", {})
        if metadata:
            prompt_identity = {
                "promptSpecVersion": metadata.get("promptSpecVersion"),
                "stagePromptChecksum": metadata.get("stagePromptChecksum"),
                "packetTemplateChecksum": metadata.get("packetTemplateChecksum"),
                "stagePromptName": metadata.get("stagePromptName"),
                "packetTemplateVersion": metadata.get("packetTemplateVersion"),
            }
            break
    statuses = [entry.get("overallStageVerdict", "EVIDENCE_GAP") for entry in validation_evidence]
    if not statuses:
        overall = "EVIDENCE_GAP"
    elif "FAIL" in statuses:
        overall = "FAIL"
    elif "PASS_WITH_LIMITS" in statuses:
        overall = "PASS_WITH_LIMITS"
    elif all(status == "PASS" for status in statuses):
        overall = "PASS"
    else:
        overall = "EVIDENCE_GAP"
    return {
        "stageName": stage,
        "promptIdentity": prompt_identity,
        "baselineEvidenceCount": len(baseline_evidence),
        "validationEvidenceCount": len(validation_evidence),
        "baselineEvidence": baseline_evidence,
        "validationEvidence": validation_evidence,
        "overallStageVerdict": overall,
    }


def markdown_report(payload: dict) -> str:
    lines = [
        "# Prompt Redesign Validation Report",
        "",
        f"- generatedAt: `{payload['generatedAt']}`",
        f"- validationCommit: `{payload['validationCommit']}`",
        f"- baselineRoots: `{', '.join(payload['baselineRoots']) or 'none'}`",
        f"- validationRoots: `{', '.join(payload['validationRoots']) or 'none'}`",
        f"- rerunExecuted: `{payload['rerunExecuted']}`",
        "",
        "This report validates stage-level prompt redesign evidence. It is not an authority-expansion report.",
        "",
        "## Stage Verdicts",
        "",
        "| stage | verdict | baseline | validation | prompt checksum | packet checksum |",
        "|---|---|---:|---:|---|---|",
    ]
    for stage in payload["stageReports"]:
        prompt = stage.get("promptIdentity", {})
        lines.append(
            f"| `{stage['stageName']}` | `{stage['overallStageVerdict']}` | "
            f"{stage['baselineEvidenceCount']} | {stage['validationEvidenceCount']} | "
            f"`{prompt.get('stagePromptChecksum', 'missing')}` | "
            f"`{prompt.get('packetTemplateChecksum', 'missing')}` |"
        )
    lines.extend(["", "## Notes", ""])
    for stage in payload["stageReports"]:
        lines.append(f"### `{stage['stageName']}`")
        if not stage["validationEvidence"]:
            lines.append("- validation evidence: missing")
            lines.append("- result: `EVIDENCE_GAP`")
            lines.append("")
            continue
        for evidence in stage["validationEvidence"]:
            lines.append(
                f"- `{evidence['scenarioPack']}/{evidence['workloadSize']}/{evidence['decisionMode']}` "
                f"context=`{evidence['contextCoverageStatus']}` "
                f"fallback=`{evidence['fallbackStatus']}` "
                f"assessment=`{evidence['assessmentRichnessStatus']}` "
                f"overall=`{evidence['overallStageVerdict']}`"
            )
            lines.append(
                f"  candidateCountSeen={evidence.get('promptMetadata', {}).get('candidateCountSeen', 'missing')} "
                f"comparisonCoverage={evidence.get('promptMetadata', {}).get('comparisonPackCoverage', 'missing')} "
                f"geospatialCoverage={evidence.get('promptMetadata', {}).get('geospatialCoverage', 'missing')}"
            )
            lines.append(
                f"  fallbackReason=`{evidence.get('fallbackSummary', {}).get('fallbackReason', '')}` "
                f"richnessScore=`{evidence.get('assessmentSummary', {}).get('richnessScore', 'missing')}` "
                f"selected/nonSelected=`{evidence.get('assessmentSummary', {}).get('selectedCount', 0)}/"
                f"{evidence.get('assessmentSummary', {}).get('nonSelectedCount', 0)}`"
            )
        if stage["baselineEvidence"]:
            lines.append(f"- baseline evidence count: `{stage['baselineEvidenceCount']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(payload: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"prompt-redesign-validation-{timestamp}.json"
    markdown_path = output_dir / "prompt_redesign_validation_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(payload), encoding="utf-8")
    return json_path, markdown_path


def planned_cells(stages: Sequence[str]) -> list[ValidationCell]:
    return [ValidationCell(stage=stage, **STAGE_DEFAULTS[stage]) for stage in stages]


def run_validation_cell(cell: ValidationCell, output_dir: Path, runner=subprocess.run) -> int:
    command = benchmark_command() + [
        "--baseline", cell.baseline,
        "--size", cell.size,
        "--scenario-pack", cell.scenario_pack,
        "--decision-mode", cell.decision_mode,
        "--execution-mode", cell.execution_mode,
        "--output-dir", str(output_dir),
    ]
    completed = runner(command, cwd=REPO_ROOT, text=True, check=False)
    return int(completed.returncode)


def collect_stage_reports(baseline_roots: Sequence[Path], validation_roots: Sequence[Path], stages: Sequence[str]) -> dict:
    benchmark_index: dict[tuple[str, str, str, str, str], dict] = {}
    feedback_rows: list[StageFeedback] = []
    for root_type, roots in (("baseline", baseline_roots), ("validation", validation_roots)):
        for root in roots:
            for result in collect_benchmark_results(root, root_type):
                benchmark_index[(result["_rootType"], result["_rootPath"], str(result.get("scenarioPack", "")), str(result.get("workloadSize", "")), str(result.get("decisionMode", "")))] = result
            feedback_rows.extend(collect_feedback_rows(root, root_type))

    baseline_stage_reports: dict[str, list[dict]] = {stage: [] for stage in stages}
    validation_stage_reports: dict[str, list[dict]] = {stage: [] for stage in stages}
    for feedback in feedback_rows:
        if feedback.stage not in stages:
            continue
        benchmark_result = benchmark_index.get((feedback.root_type, feedback.root_path, feedback.scenario_pack, feedback.size, feedback.decision_mode))
        evidence = build_stage_evidence(feedback, benchmark_result)
        target = baseline_stage_reports if feedback.root_type == "baseline" else validation_stage_reports
        target[feedback.stage].append(evidence)

    stage_reports = [build_stage_report(stage, baseline_stage_reports.get(stage, []), validation_stage_reports.get(stage, [])) for stage in stages]
    return {
        "stageReports": stage_reports,
        "baselineEvidenceCount": sum(len(items) for items in baseline_stage_reports.values()),
        "validationEvidenceCount": sum(len(items) for items in validation_stage_reports.values()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 prompt redesign stage validation.")
    parser.add_argument("--baseline-root", action="append", default=[])
    parser.add_argument("--validation-root", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--stage", action="append", choices=stage_cli_choices(), default=[])
    parser.add_argument("--rerun-cells", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    stages = args.stage or list(TARGET_STAGES)
    output_dir = Path(args.output_dir)
    baseline_roots = [Path(path) for path in (args.baseline_root or [str(DEFAULT_BASELINE_ROOT)])]
    validation_roots = [Path(path) for path in args.validation_root]
    cells = planned_cells(stages)
    print(f"[PROMPT VALIDATION] stage-count={len(cells)}")
    for cell in cells:
        print(
            f"- stage={cell.stage} scenario-pack={cell.scenario_pack} size={cell.size} "
            f"decision-mode={cell.decision_mode} baseline={cell.baseline} execution-mode={cell.execution_mode}"
        )
    if args.dry_run:
        return 0

    rerun_executed = False
    if args.rerun_cells:
        live_root = output_dir / "live"
        validation_roots.append(live_root)
        rerun_executed = True
        for cell in cells:
            print(f"[CELL STARTED] stage={cell.stage}")
            exit_code = run_validation_cell(cell, live_root)
            if exit_code != 0:
                print(f"[CELL FAILED] stage={cell.stage} exit={exit_code}")
                return exit_code
            print(f"[CELL COMPLETED] stage={cell.stage}")

    summary = collect_stage_reports(baseline_roots, validation_roots, stages)
    payload = {
        "schemaVersion": "dispatch-prompt-redesign-validation/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "validationCommit": git_commit(),
        "baselineRoots": [str(path) for path in baseline_roots],
        "validationRoots": [str(path) for path in validation_roots],
        "rerunExecuted": rerun_executed,
        "targetStages": list(stages),
        "baselineEvidenceCount": summary["baselineEvidenceCount"],
        "validationEvidenceCount": summary["validationEvidenceCount"],
        "stageReports": summary["stageReports"],
    }
    json_path, markdown_path = write_report(payload, output_dir)
    print(f"[REPORT JSON] {json_path}")
    print(f"[REPORT MARKDOWN] {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
