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
DEFAULT_BASELINE_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "phase2-live3"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark" / "prompt-redesign"
DEFAULT_PROVIDER_VALIDATION_DIR = REPO_ROOT / "artifacts" / "validation" / "llm-provider"
TARGET_STAGES = (
    "pair-bundle",
    "route-generation",
    "route-critique",
    "scenario",
    "final-selection",
)
PROMPT_FAMILIES = ("v2", "v3")
STAGE_DEFAULTS = {
    "pair-bundle": {"scenario_pack": "normal-clear", "size": "S", "baseline": "C", "decision_mode": "legacy", "execution_mode": "controlled"},
    "route-generation": {"scenario_pack": "heavy-rain", "size": "S", "baseline": "C", "decision_mode": "legacy", "execution_mode": "controlled"},
    "route-critique": {"scenario_pack": "traffic-shock", "size": "S", "baseline": "C", "decision_mode": "legacy", "execution_mode": "controlled"},
    "scenario": {"scenario_pack": "forecast-heavy", "size": "S", "baseline": "C", "decision_mode": "legacy", "execution_mode": "controlled"},
    "final-selection": {"scenario_pack": "normal-clear", "size": "S", "baseline": "C", "decision_mode": "legacy", "execution_mode": "controlled"},
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
    "promptFamily",
    "promptSpecVersion",
    "stagePromptName",
    "stagePromptChecksum",
    "packetTemplateVersion",
    "packetTemplateChecksum",
    "skillSetVersion",
    "skillIdsActivated",
    "candidateCountSeen",
    "comparisonPackCoverage",
    "geospatialCoverage",
    "missingContextFlags",
    "visibilityProfile",
    "comparisonLens",
    "geospatialLens",
    "fallbackReason",
    "sessionStoreEnabled",
    "sessionNamespace",
    "sessionReadRefs",
    "sessionWriteRefs",
    "sessionRefCount",
)
COMPARISON_VERDICTS = ("IDENTITY_ONLY", "RICHER_ASSESSMENT", "NO_CLEAR_GAIN", "REGRESSION_RISK", "EVIDENCE_GAP")


@dataclass(frozen=True)
class ValidationCell:
    stage: str
    prompt_family: str
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
    prompt_family: str
    authority_phase: str
    trace_id: str
    stage: str
    families: Dict[str, dict]


def stage_cli_choices() -> List[str]:
    return list(TARGET_STAGES)


def prompt_family_choices() -> List[str]:
    return [*PROMPT_FAMILIES, "both"]


def benchmark_command() -> List[str]:
    if os.name == "nt" and shutil.which("py"):
        return ["py", "-3.13", str(REPO_ROOT / "scripts" / "run_dispatch_v2_benchmark.py")]
    return ["python", str(REPO_ROOT / "scripts" / "run_dispatch_v2_benchmark.py")]


def provider_probe_command() -> List[str]:
    raise RuntimeError("LLM provider probing is disabled by policy.")


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def run_provider_responses_preflight(output_dir: Path, runner=subprocess.run) -> dict:
    if truthy(os.environ.get("LLM_PROVIDER_RESPONSES_READY")):
        return {
            "schemaVersion": "llm-provider-responses-preflight/v1",
            "ready": True,
            "source": "env",
            "selectedModel": os.environ.get("ROUTECHAIN_DECISION_LLM_MODEL", ""),
            "results": [],
            "exitCode": 0,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    before = set(output_dir.glob("responses_probe-*.json"))
    completed = runner(provider_probe_command() + ["--output-dir", str(output_dir)], cwd=REPO_ROOT, text=True, check=False)
    after = set(output_dir.glob("responses_probe-*.json"))
    created = sorted(after - before, key=lambda path: path.stat().st_mtime)
    latest = created[-1] if created else max(after, key=lambda path: path.stat().st_mtime, default=None)
    if latest is None:
        return {
            "schemaVersion": "llm-provider-responses-preflight/v1",
            "ready": False,
            "source": "probe-missing-artifact",
            "selectedModel": None,
            "results": [],
            "exitCode": int(completed.returncode),
            "failureReason": "provider-responses-probe-artifact-missing",
        }
    payload = json_read(latest)
    payload["source"] = "probe"
    payload["artifactPath"] = str(latest)
    payload["exitCode"] = int(completed.returncode)
    return payload


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


def family_roots(prompt_family: str) -> List[str]:
    return list(PROMPT_FAMILIES) if prompt_family == "both" else [prompt_family]


def parse_stage_feedback(path: Path, root_type: str, root_path: Path) -> Optional[StageFeedback]:
    parts = path.parts
    try:
        feedback_index = parts.index("feedback")
        decision_stage_index = parts.index("decision-stage")
    except ValueError:
        return None
    if decision_stage_index - feedback_index < 6:
        return None
    payload = json_read(path)
    prompt_family_index = feedback_index + 5
    prompt_family = "v2"
    authority_phase_index = prompt_family_index
    if len(parts) > prompt_family_index and parts[prompt_family_index] in PROMPT_FAMILIES:
        prompt_family = parts[prompt_family_index]
        authority_phase_index += 1
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
        prompt_family=prompt_family,
        authority_phase=parts[authority_phase_index],
        trace_id=trace_id,
        stage=stage,
        families={parts[decision_stage_index + 1]: payload},
    )


def merge_feedback_rows(rows: Iterable[StageFeedback]) -> Dict[Tuple[str, str, str, str, str, str, str, str, str], StageFeedback]:
    merged: Dict[Tuple[str, str, str, str, str, str, str, str, str], StageFeedback] = {}
    for row in rows:
        key = (
            row.root_type,
            row.root_path,
            row.scenario_pack,
            row.size,
            row.execution_mode,
            row.decision_mode,
            row.prompt_family,
            row.authority_phase,
            row.trace_id,
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
                prompt_family=existing.prompt_family,
                authority_phase=existing.authority_phase,
                trace_id=existing.trace_id,
                stage=existing.stage,
                families=families,
            )
    return merged


def collect_feedback_rows(root: Path, root_type: str) -> List[StageFeedback]:
    feedback_root = root / "feedback"
    if not feedback_root.exists():
        return []
    rows = [parsed for path in feedback_root.rglob("*.json") if (parsed := parse_stage_feedback(path, root_type, root)) is not None]
    return list(merge_feedback_rows(rows).values())


def collect_benchmark_results(root: Path, root_type: str) -> List[dict]:
    if not root.exists():
        return []
    results: List[dict] = []
    for path in sorted(root.rglob("dispatch-quality*.json")):
        payload = json_read(path)
        if "baselineId" not in payload:
            continue
        payload["_rootType"] = root_type
        payload["_rootPath"] = str(root)
        payload["_artifactPath"] = str(path)
        payload.setdefault("promptFamily", "v2")
        results.append(payload)
    return results


def flatten_assessment_items(assessments: object) -> List[dict]:
    if not isinstance(assessments, dict):
        return []
    if isinstance(assessments.get("items"), list):
        return [item for item in assessments["items"] if isinstance(item, dict)]
    items: List[dict] = []
    for value in assessments.values():
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            items.extend(item for item in value["items"] if isinstance(item, dict))
    return items


def count_selected_and_non_selected(items: List[dict], join_payload: Optional[dict]) -> Tuple[int, int, bool]:
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


def merged_prompt_payload(feedback: StageFeedback) -> dict:
    merged: Dict[str, object] = {}
    for family in ("llm_prompt_spec_trace", "llm_skill_activation_trace", "decision_session_ref_trace", "decision_session_stage_summary"):
        payload = feedback.families.get(family, {})
        if isinstance(payload, dict):
            merged.update(payload)
    merged.setdefault("promptFamily", feedback.prompt_family)
    return merged


def prompt_metadata_summary(feedback: StageFeedback) -> dict:
    prompt = merged_prompt_payload(feedback)
    return {field: prompt.get(field) for field in PROMPT_METADATA_FIELDS if field in prompt}


def prompt_identity_locked(metadata: dict) -> bool:
    return (
        bool(metadata)
        and metadata.get("promptSpecVersion") not in (None, "", "generic-fallback/v1")
        and metadata.get("stagePromptChecksum") not in (None, "")
        and metadata.get("packetTemplateChecksum") not in (None, "")
    )


def context_verdict(metadata: dict) -> Tuple[str, List[str]]:
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


def assessment_richness(items: List[dict]) -> Optional[float]:
    if not items:
        return None
    total = 0.0
    for item in items:
        present = sum(1 for field in EXPECTED_ASSESSMENT_FIELDS if field in item)
        total += present / len(EXPECTED_ASSESSMENT_FIELDS)
    return total / len(items)


def assessment_verdict(items: List[dict], join_payload: Optional[dict]) -> Tuple[str, dict]:
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


def fallback_verdict(output_payload: dict, prompt_meta: dict) -> Tuple[str, dict]:
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


def build_stage_evidence(feedback: StageFeedback, benchmark_result: Optional[dict]) -> dict:
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
            "promptFamily": benchmark_result.get("promptFamily", feedback.prompt_family),
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
        "promptFamily": feedback.prompt_family,
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


def summarize_family(stage: str, family: str, baseline_evidence: List[dict], validation_evidence: List[dict]) -> dict:
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
                "skillSetVersion": metadata.get("skillSetVersion", ""),
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
    richness_values = [entry.get("assessmentSummary", {}).get("richnessScore") for entry in validation_evidence]
    richness_values = [float(value) for value in richness_values if value is not None]
    session_ref_counts = [int(entry.get("promptMetadata", {}).get("sessionRefCount", 0) or 0) for entry in validation_evidence]
    return {
        "stageName": stage,
        "promptFamily": family,
        "promptIdentity": prompt_identity,
        "baselineEvidenceCount": len(baseline_evidence),
        "validationEvidenceCount": len(validation_evidence),
        "baselineEvidence": baseline_evidence,
        "validationEvidence": validation_evidence,
        "overallVerdict": overall,
        "maxRichnessScore": max(richness_values) if richness_values else None,
        "fallbackUsed": any(bool(entry.get("fallbackSummary", {}).get("fallbackUsed")) for entry in validation_evidence),
        "promptIdentityLocked": any(bool(entry.get("promptIdentityLocked")) for entry in validation_evidence),
        "sessionRefCountMax": max(session_ref_counts) if session_ref_counts else 0,
    }


def compare_families(v2_report: Optional[dict], v3_report: Optional[dict]) -> dict:
    if v2_report is None or v3_report is None:
        return {"verdict": "EVIDENCE_GAP", "reasons": ["missing-family-evidence"]}
    if not v2_report["validationEvidence"] or not v3_report["validationEvidence"]:
        return {"verdict": "EVIDENCE_GAP", "reasons": ["missing-validation-evidence"]}
    if not v3_report["promptIdentityLocked"]:
        return {"verdict": "EVIDENCE_GAP", "reasons": ["v3-prompt-identity-unlocked"]}
    if v3_report["overallVerdict"] == "FAIL" and v2_report["overallVerdict"] != "FAIL":
        return {"verdict": "REGRESSION_RISK", "reasons": ["v3-stage-verdict-regressed"]}
    if v3_report["fallbackUsed"] and not v2_report["fallbackUsed"]:
        return {"verdict": "REGRESSION_RISK", "reasons": ["v3-fallback-increase"]}
    v2_richness = v2_report.get("maxRichnessScore")
    v3_richness = v3_report.get("maxRichnessScore")
    if v2_richness is not None and v3_richness is not None and v3_richness >= v2_richness + 0.10:
        return {"verdict": "RICHER_ASSESSMENT", "reasons": ["v3-richness-score-higher"]}
    if v3_report.get("sessionRefCountMax", 0) > 0 and v2_richness == v3_richness:
        return {"verdict": "IDENTITY_ONLY", "reasons": ["v3-session-evidence-present-without-richness-gain"]}
    return {"verdict": "NO_CLEAR_GAIN", "reasons": ["paired-comparison-no-clear-uplift"]}


def build_stage_report(stage: str, baseline_evidence: List[dict], validation_evidence: List[dict]) -> dict:
    family_reports: Dict[str, dict] = {}
    for family in PROMPT_FAMILIES:
        family_reports[family] = summarize_family(
            stage,
            family,
            [entry for entry in baseline_evidence if entry.get("promptFamily", "v2") == family],
            [entry for entry in validation_evidence if entry.get("promptFamily", "v2") == family],
        )
    paired = compare_families(family_reports.get("v2"), family_reports.get("v3"))
    overall = family_reports["v3"]["overallVerdict"] if family_reports["v3"]["validationEvidence"] else family_reports["v2"]["overallVerdict"]
    return {
        "stageName": stage,
        "familyReports": family_reports,
        "pairedComparison": paired,
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
        f"- promptFamilyMode: `{payload['promptFamilyMode']}`",
    ]
    preflight = payload.get("providerResponsesPreflight") if isinstance(payload.get("providerResponsesPreflight"), dict) else None
    if preflight is not None:
        lines.extend([
            f"- providerResponsesReady: `{preflight.get('ready', False)}`",
            f"- providerResponsesSource: `{preflight.get('source', '')}`",
            f"- providerResponsesSelectedModel: `{preflight.get('selectedModel') or 'none'}`",
        ])
    lines.extend([
        "",
        "This report validates prompt identity, stage-scoped context coverage, and paired v2/v3 evidence. It does not claim authority uplift.",
        "",
        "## Stage Verdicts",
        "",
        "| stage | v2 verdict | v3 verdict | paired comparison | v2 checksum | v3 checksum |",
        "|---|---|---|---|---|---|",
    ])
    for stage in payload["stageReports"]:
        v2 = stage["familyReports"]["v2"]
        v3 = stage["familyReports"]["v3"]
        lines.append(
            f"| `{stage['stageName']}` | `{v2['overallVerdict']}` | `{v3['overallVerdict']}` | "
            f"`{stage['pairedComparison']['verdict']}` | "
            f"`{v2['promptIdentity'].get('stagePromptChecksum', 'missing')}` | "
            f"`{v3['promptIdentity'].get('stagePromptChecksum', 'missing')}` |"
        )
    lines.extend(["", "## Notes", ""])
    for stage in payload["stageReports"]:
        lines.append(f"### `{stage['stageName']}`")
        lines.append(f"- paired comparison: `{stage['pairedComparison']['verdict']}` reasons=`{stage['pairedComparison']['reasons']}`")
        for family in PROMPT_FAMILIES:
            family_report = stage["familyReports"][family]
            lines.append(
                f"- `{family}` verdict=`{family_report['overallVerdict']}` "
                f"validationEvidence=`{family_report['validationEvidenceCount']}` "
                f"baselineEvidence=`{family_report['baselineEvidenceCount']}` "
                f"maxRichness=`{family_report['maxRichnessScore']}` "
                f"sessionRefCountMax=`{family_report['sessionRefCountMax']}`"
            )
            if not family_report["validationEvidence"]:
                continue
            for evidence in family_report["validationEvidence"]:
                lines.append(
                    f"  {evidence['scenarioPack']}/{evidence['workloadSize']}/{evidence['decisionMode']} "
                    f"context=`{evidence['contextCoverageStatus']}` fallback=`{evidence['fallbackStatus']}` "
                    f"assessment=`{evidence['assessmentRichnessStatus']}` overall=`{evidence['overallStageVerdict']}`"
                )
                lines.append(
                    f"  candidateCountSeen={evidence.get('promptMetadata', {}).get('candidateCountSeen', 'missing')} "
                    f"comparisonCoverage={evidence.get('promptMetadata', {}).get('comparisonPackCoverage', 'missing')} "
                    f"geospatialCoverage={evidence.get('promptMetadata', {}).get('geospatialCoverage', 'missing')} "
                    f"skillSetVersion={evidence.get('promptMetadata', {}).get('skillSetVersion', '')} "
                    f"sessionRefCount={evidence.get('promptMetadata', {}).get('sessionRefCount', 0)}"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(payload: dict, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"prompt-redesign-validation-{timestamp}.json"
    markdown_path = output_dir / "prompt_redesign_validation_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(payload), encoding="utf-8")
    return json_path, markdown_path


def planned_cells(stages: Sequence[str], prompt_family_mode: str) -> List[ValidationCell]:
    families = family_roots(prompt_family_mode)
    return [ValidationCell(stage=stage, prompt_family=family, **STAGE_DEFAULTS[stage]) for stage in stages for family in families]


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
    completed = runner(command, cwd=REPO_ROOT, text=True, check=False)
    return int(completed.returncode)


def preflight_gap_stage_reports(stages: Sequence[str], prompt_family_mode: str) -> List[dict]:
    families = family_roots(prompt_family_mode)
    reports = []
    for stage in stages:
        family_reports = {}
        for family in PROMPT_FAMILIES:
            family_reports[family] = {
                "stageName": stage,
                "promptFamily": family,
                "promptIdentity": {},
                "baselineEvidenceCount": 0,
                "validationEvidenceCount": 0,
                "baselineEvidence": [],
                "validationEvidence": [],
                "overallVerdict": "EVIDENCE_GAP",
                "maxRichnessScore": None,
                "fallbackUsed": False,
                "promptIdentityLocked": False,
                "sessionRefCountMax": 0,
            }
        reason = "provider-responses-not-ready"
        reports.append({
            "stageName": stage,
            "familyReports": family_reports,
            "pairedComparison": {"verdict": "EVIDENCE_GAP", "reasons": [reason]},
            "overallStageVerdict": "EVIDENCE_GAP",
            "evidenceGapReason": reason,
            "targetPromptFamilies": families,
        })
    return reports


def collect_stage_reports(baseline_roots: Sequence[Path], validation_roots: Sequence[Path], stages: Sequence[str]) -> dict:
    benchmark_index: Dict[Tuple[str, str, str, str, str, str, str], dict] = {}
    feedback_rows: List[StageFeedback] = []
    for root_type, roots in (("baseline", baseline_roots), ("validation", validation_roots)):
        for root in roots:
            for result in collect_benchmark_results(root, root_type):
                benchmark_index[(
                    result["_rootType"],
                    result["_rootPath"],
                    str(result.get("scenarioPack", "")),
                    str(result.get("workloadSize", "")),
                    str(result.get("decisionMode", "")),
                    str(result.get("executionMode", "")),
                    str(result.get("promptFamily", "v2")),
                )] = result
            feedback_rows.extend(collect_feedback_rows(root, root_type))

    baseline_stage_reports: Dict[str, List[dict]] = {stage: [] for stage in stages}
    validation_stage_reports: Dict[str, List[dict]] = {stage: [] for stage in stages}
    for feedback in feedback_rows:
        if feedback.stage not in stages:
            continue
        benchmark_result = benchmark_index.get((
            feedback.root_type,
            feedback.root_path,
            feedback.scenario_pack,
            feedback.size,
            feedback.decision_mode,
            feedback.execution_mode,
            feedback.prompt_family,
        ))
        evidence = build_stage_evidence(feedback, benchmark_result)
        target = baseline_stage_reports if feedback.root_type == "baseline" else validation_stage_reports
        target[feedback.stage].append(evidence)

    stage_reports = [build_stage_report(stage, baseline_stage_reports.get(stage, []), validation_stage_reports.get(stage, [])) for stage in stages]
    return {
        "stageReports": stage_reports,
        "baselineEvidenceCount": sum(len(items) for items in baseline_stage_reports.values()),
        "validationEvidenceCount": sum(len(items) for items in validation_stage_reports.values()),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 prompt redesign stage validation.")
    parser.add_argument("--baseline-root", action="append", default=[])
    parser.add_argument("--validation-root", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--stage", action="append", choices=stage_cli_choices(), default=[])
    parser.add_argument("--prompt-family", choices=prompt_family_choices(), default="both")
    parser.add_argument("--rerun-cells", action="store_true")
    parser.add_argument("--skip-provider-responses-preflight", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "dispatch-prompt-redesign-validation/v2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rerunExecuted": False,
        "verdict": "DISABLED",
        "reason": "llm-disabled-by-policy",
        "providerResponsesPreflight": {
            "ready": False,
            "failureReason": "llm-disabled-by-policy",
        },
    }
    output_path = output_dir / "prompt_redesign_validation_disabled.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[PROMPT VALIDATION DISABLED] reason=llm-disabled-by-policy json={output_path}")
    return 2

    stages = args.stage or list(TARGET_STAGES)
    output_dir = Path(args.output_dir)
    baseline_roots = [Path(path) for path in (args.baseline_root or [str(DEFAULT_BASELINE_ROOT)])]
    validation_roots = [Path(path) for path in args.validation_root]
    cells = planned_cells(stages, args.prompt_family)
    print(f"[PROMPT VALIDATION] stage-count={len(cells)}")
    for cell in cells:
        print(
            f"- stage={cell.stage} prompt-family={cell.prompt_family} scenario-pack={cell.scenario_pack} size={cell.size} "
            f"decision-mode={cell.decision_mode} baseline={cell.baseline} execution-mode={cell.execution_mode}"
        )
    if args.dry_run:
        return 0

    provider_preflight = None
    if args.rerun_cells and not args.skip_provider_responses_preflight:
        provider_preflight = run_provider_responses_preflight(DEFAULT_PROVIDER_VALIDATION_DIR)
        if not bool(provider_preflight.get("ready")):
            payload = {
                "schemaVersion": "dispatch-prompt-redesign-validation/v2",
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "validationCommit": git_commit(),
                "baselineRoots": [str(path) for path in baseline_roots],
                "validationRoots": [str(path) for path in validation_roots],
                "rerunExecuted": False,
                "promptFamilyMode": args.prompt_family,
                "targetStages": list(stages),
                "baselineEvidenceCount": 0,
                "validationEvidenceCount": 0,
                "stageReports": preflight_gap_stage_reports(stages, args.prompt_family),
                "comparisonVerdicts": list(COMPARISON_VERDICTS),
                "providerResponsesPreflight": provider_preflight,
            }
            json_path, markdown_path = write_report(payload, output_dir)
            print("[PROVIDER RESPONSES NOT READY] prompt validation skipped")
            print(f"[REPORT JSON] {json_path}")
            print(f"[REPORT MARKDOWN] {markdown_path}")
            return 1

    rerun_executed = False
    if args.rerun_cells:
        rerun_executed = True
        for cell in cells:
            live_root = output_dir / "live" / cell.prompt_family
            if live_root not in validation_roots:
                validation_roots.append(live_root)
            print(f"[CELL STARTED] stage={cell.stage} prompt-family={cell.prompt_family}")
            exit_code = run_validation_cell(cell, live_root)
            if exit_code != 0:
                print(f"[CELL FAILED] stage={cell.stage} prompt-family={cell.prompt_family} exit={exit_code}")
                return exit_code
            print(f"[CELL COMPLETED] stage={cell.stage} prompt-family={cell.prompt_family}")

    summary = collect_stage_reports(baseline_roots, validation_roots, stages)
    payload = {
        "schemaVersion": "dispatch-prompt-redesign-validation/v2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "validationCommit": git_commit(),
        "baselineRoots": [str(path) for path in baseline_roots],
        "validationRoots": [str(path) for path in validation_roots],
        "rerunExecuted": rerun_executed,
        "promptFamilyMode": args.prompt_family,
        "targetStages": list(stages),
        "baselineEvidenceCount": summary["baselineEvidenceCount"],
        "validationEvidenceCount": summary["validationEvidenceCount"],
        "stageReports": summary["stageReports"],
        "comparisonVerdicts": list(COMPARISON_VERDICTS),
        "providerResponsesPreflight": provider_preflight,
    }
    json_path, markdown_path = write_report(payload, output_dir)
    print(f"[REPORT JSON] {json_path}")
    print(f"[REPORT MARKDOWN] {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
