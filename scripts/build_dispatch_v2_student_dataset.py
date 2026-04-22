from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


FAMILIES = (
    "decision_stage_input",
    "decision_stage_output",
    "decision_stage_join",
    "dispatch_execution",
    "dispatch_outcome",
    "route_leg_vector_trace",
    "route_vector_summary_trace",
    "llm_reasoning_cycle_trace",
)


def discover_feedback_roots(feedback_root: Path) -> list[Path]:
    direct_root = feedback_root / "decision-stage"
    if direct_root.exists():
        return [feedback_root]
    discovered = sorted({path.parent for path in feedback_root.rglob("decision-stage") if path.is_dir()})
    return discovered


def load_family_files(feedback_root: Path) -> dict[str, list[Path]]:
    base = feedback_root / "decision-stage"
    family_files: dict[str, list[Path]] = {}
    for family in FAMILIES:
        family_dir = base / family
        family_files[family] = sorted(family_dir.glob("*.json")) if family_dir.exists() else []
    return family_files


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def trace_id_from_filename(path: Path, family: str | None = None) -> str:
    name = path.stem
    if family == "dispatch_execution" and name.endswith("-dispatch-executor"):
        return name[: -len("-dispatch-executor")].strip()
    if family == "dispatch_outcome" and name.endswith("-dispatch-result"):
        return name[: -len("-dispatch-result")].strip()
    if "-" not in name:
        return ""
    return name.split("-", 1)[0].strip()


def group_by_trace(paths: list[Path], family: str | None = None) -> dict[str, list]:
    grouped: dict[str, list] = defaultdict(list)
    for path in paths:
        payload = load_json(path)
        if isinstance(payload, dict):
            trace_id = str(payload.get("traceId") or payload.get("trace_id") or "").strip()
            if not trace_id and family in {"route_vector_summary_trace", "route_leg_vector_trace"}:
                proposal_id = str(payload.get("proposalId") or payload.get("proposal_id") or "").strip()
                if proposal_id:
                    proposal_suffix = "-" + sanitize_name(proposal_id)
                    if path.stem.endswith(proposal_suffix):
                        trace_id = path.stem[: -len(proposal_suffix)].strip()
            if not trace_id:
                trace_id = trace_id_from_filename(path, family)
        else:
            trace_id = trace_id_from_filename(path, family)
        if not trace_id:
            continue
        grouped[trace_id].append(payload)
    return grouped


def validate_family_schema_versions(family_files: dict[str, list[Path]]) -> None:
    for family, paths in family_files.items():
        versions = {
            str(load_json(path).get("schemaVersion") or "").strip()
            for path in paths
            if str(load_json(path).get("schemaVersion") or "").strip()
        }
        if len(versions) > 1:
            raise ValueError(f"Mixed schema versions detected in family '{family}': {sorted(versions)}")


def sanitize_name(raw: str) -> str:
    return "".join(character if character.isalnum() or character in "._-" else "_" for character in raw)


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def matches_filter_value(payload: dict, keys: tuple[str, ...], expected: str | None, feedback_root: Path) -> bool:
    if not expected:
        return True
    normalized_expected = expected.strip().lower()
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip().lower() == normalized_expected:
            return True
    return normalized_expected in {part.lower() for part in feedback_root.parts}


def build_rows(
    grouped: dict[str, dict[str, list[dict]]],
    feedback_root: Path,
    authority_mode: str | None,
    trace_roots: dict[str, Path],
    stage_filters: set[str] | None = None,
    scenario_pack: str | None = None,
    decision_mode: str | None = None,
    authority_phase: str | None = None,
    route_vector_availability: str = "any",
) -> dict[str, list[dict]]:
    trace_ids = sorted({trace_id for families in grouped.values() for trace_id in families.keys()})
    outputs = {
        "stage_inputs": [],
        "stage_outputs": [],
        "stage_joins": [],
        "dispatch_execution": [],
        "dispatch_outcomes": [],
        "route_vectors": [],
        "llm_reasoning_cycles": [],
    }

    for trace_id in trace_ids:
        trace_root = trace_roots.get(trace_id, feedback_root)
        has_route_vectors = bool(grouped["route_vector_summary_trace"].get(trace_id, []))
        if route_vector_availability == "required" and not has_route_vectors:
            continue
        if route_vector_availability == "none" and has_route_vectors:
            continue
        route_vector_refs = [
            row.get("proposalId")
            for row in grouped["route_vector_summary_trace"].get(trace_id, [])
            if row.get("proposalId")
        ]
        route_leg_rows = grouped["route_leg_vector_trace"].get(trace_id, [])
        for row in grouped["decision_stage_input"].get(trace_id, []):
            stage_name = row.get("stageName")
            if stage_filters and stage_name not in stage_filters:
                continue
            if not matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root):
                continue
            if not matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root):
                continue
            if not matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root):
                continue
            outputs["stage_inputs"].append({
                "traceId": trace_id,
                "tickId": row.get("tickId"),
                "stageName": stage_name,
                "brainType": None,
                "authorityMode": authority_mode,
                "selectedIds": [],
                "outcomeRefs": [],
                "routeVectorRefs": route_vector_refs,
                "payload": row,
            })
        for row in grouped["decision_stage_output"].get(trace_id, []):
            stage_name = row.get("stageName")
            if stage_filters and stage_name not in stage_filters:
                continue
            if not matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root):
                continue
            if not matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root):
                continue
            if not matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root):
                continue
            outputs["stage_outputs"].append({
                "traceId": trace_id,
                "tickId": row.get("tickId"),
                "stageName": stage_name,
                "brainType": row.get("brainType"),
                "authorityMode": authority_mode,
                "selectedIds": row.get("selectedIds", []),
                "outcomeRefs": [],
                "routeVectorRefs": route_vector_refs,
                "payload": row,
            })
        for row in grouped["decision_stage_join"].get(trace_id, []):
            stage_name = row.get("stageName")
            if stage_filters and stage_name not in stage_filters:
                continue
            if not matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root):
                continue
            if not matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root):
                continue
            if not matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root):
                continue
            outputs["stage_joins"].append({
                "traceId": trace_id,
                "tickId": row.get("tickId"),
                "stageName": stage_name,
                "brainType": row.get("brainType"),
                "authorityMode": authority_mode,
                "selectedIds": row.get("selectedIds", []),
                "outcomeRefs": row.get("actualSelectedIds", []),
                "routeVectorRefs": route_vector_refs,
                "payload": row,
            })
        for row in grouped["dispatch_execution"].get(trace_id, []):
            if not matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root):
                continue
            if not matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root):
                continue
            if not matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root):
                continue
            outputs["dispatch_execution"].append({
                "traceId": trace_id,
                "tickId": None,
                "stageName": "dispatch-execution",
                "brainType": None,
                "authorityMode": authority_mode,
                "selectedIds": [],
                "outcomeRefs": row.get("assignmentIds", []),
                "routeVectorRefs": route_vector_refs,
                "payload": row,
            })
        for row in grouped["dispatch_outcome"].get(trace_id, []):
            if not matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root):
                continue
            if not matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root):
                continue
            if not matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root):
                continue
            outputs["dispatch_outcomes"].append({
                "traceId": trace_id,
                "tickId": None,
                "stageName": "dispatch-outcome",
                "brainType": None,
                "authorityMode": authority_mode,
                "selectedIds": [],
                "outcomeRefs": row.get("selectedProposalIds", []),
                "routeVectorRefs": route_vector_refs,
                "payload": row,
            })
        for row in grouped["route_vector_summary_trace"].get(trace_id, []):
            if not matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root):
                continue
            if not matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root):
                continue
            if not matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root):
                continue
            outputs["route_vectors"].append({
                "traceId": trace_id,
                "tickId": None,
                "stageName": "route-vector",
                "brainType": None,
                "authorityMode": authority_mode,
                "selectedIds": [row.get("proposalId")] if row.get("proposalId") else [],
                "outcomeRefs": [],
                "routeVectorRefs": [row.get("proposalId")] if row.get("proposalId") else [],
                "vectorKind": "summary",
                "legPayloads": [
                    leg_row.get("legs", [])
                    for leg_row in route_leg_rows
                    if isinstance(leg_row, dict) and leg_row.get("proposalId") == row.get("proposalId")
                ],
                "payload": row,
            })
        for row in grouped["llm_reasoning_cycle_trace"].get(trace_id, []):
            outputs["llm_reasoning_cycles"].append({
                "traceId": trace_id,
                "tickId": row.get("tickId"),
                "stageName": row.get("stageName"),
                "brainType": "llm",
                "authorityMode": authority_mode,
                "selectedIds": [],
                "outcomeRefs": [],
                "routeVectorRefs": route_vector_refs,
                "payload": row,
            })
    return outputs


def trace_matches_filters(
    trace_id: str,
    grouped: dict[str, dict[str, list[dict]]],
    trace_roots: dict[str, Path],
    stage_filters: set[str] | None,
    scenario_pack: str | None,
    decision_mode: str | None,
    authority_phase: str | None,
) -> bool:
    trace_root = trace_roots.get(trace_id)
    if trace_root is None:
        return False
    rows = []
    for family_rows in grouped.values():
        rows.extend(family_rows.get(trace_id, []))
    if not rows:
        return False
    if stage_filters:
        relevant_rows = [row for row in rows if row.get("stageName") in stage_filters]
        if not relevant_rows:
            return False
    if not any(matches_filter_value(row, ("scenarioPack", "scenario_pack"), scenario_pack, trace_root) for row in rows):
        return False
    if not any(matches_filter_value(row, ("decisionMode", "decision_mode"), decision_mode, trace_root) for row in rows):
        return False
    if not any(matches_filter_value(row, ("authorityPhase", "authority_phase", "authorityMode", "authority_mode"), authority_phase, trace_root) for row in rows):
        return False
    return True


def validate_rows(
    grouped: dict[str, dict[str, list[dict]]],
    trace_roots: dict[str, Path],
    require_route_vectors: bool,
    stage_filters: set[str] | None,
    scenario_pack: str | None,
    decision_mode: str | None,
    authority_phase: str | None,
) -> None:
    trace_ids = sorted({trace_id for families in grouped.values() for trace_id in families.keys()})
    for trace_id in trace_ids:
        if not trace_matches_filters(
            trace_id,
            grouped,
            trace_roots,
            stage_filters,
            scenario_pack,
            decision_mode,
            authority_phase,
        ):
            continue
        inputs = grouped["decision_stage_input"].get(trace_id, [])
        outputs = grouped["decision_stage_output"].get(trace_id, [])
        joins = grouped["decision_stage_join"].get(trace_id, [])
        executions = grouped["dispatch_execution"].get(trace_id, [])
        outcomes = grouped["dispatch_outcome"].get(trace_id, [])
        route_vectors = grouped["route_vector_summary_trace"].get(trace_id, [])
        if require_route_vectors and not route_vectors:
            continue
        input_stages = {(row.get("traceId"), row.get("stageName")) for row in inputs}
        output_stages = {(row.get("traceId"), row.get("stageName")) for row in outputs}
        join_stages = {(row.get("traceId"), row.get("stageName")) for row in joins}
        missing_outputs = sorted(stage for stage in input_stages if stage not in output_stages)
        if missing_outputs:
            raise ValueError(f"Missing stage outputs for trace '{trace_id}': {missing_outputs}")
        missing_joins = sorted(stage for stage in output_stages if stage not in join_stages)
        if missing_joins:
            raise ValueError(f"Missing stage joins for trace '{trace_id}': {missing_joins}")
        if outcomes and not executions:
            raise ValueError(f"Missing dispatch_execution for trace '{trace_id}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a normalized Dispatch V2 student dataset from feedback logs.")
    parser.add_argument("--feedback-root", required=True, help="Feedback base directory that contains decision-stage logs.")
    parser.add_argument("--output-dir", required=True, help="Directory to write dataset JSONL files.")
    parser.add_argument("--authority-mode", default="unknown", help="Authority mode label recorded in dataset manifest.")
    parser.add_argument("--stage", action="append", default=[], help="Optional repeated stage filter.")
    parser.add_argument("--scenario-pack", help="Optional scenario-pack filter.")
    parser.add_argument("--decision-mode", help="Optional decision-mode filter.")
    parser.add_argument("--authority-phase", help="Optional authority-phase filter.")
    parser.add_argument("--route-vector-availability", default="any", choices=("any", "required", "none"))
    parser.add_argument("--allow-partial", action="store_true", help="Allow incomplete linkage instead of failing.")
    args = parser.parse_args(argv)

    feedback_root = Path(args.feedback_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_roots = discover_feedback_roots(feedback_root)
    if not trace_roots:
        raise ValueError(f"No decision-stage directories found under '{feedback_root}'")
    trace_root_by_id: dict[str, Path] = {}
    grouped = {family: defaultdict(list) for family in FAMILIES}
    for trace_root in trace_roots:
        family_files = load_family_files(trace_root)
        validate_family_schema_versions(family_files)
        for family, paths in family_files.items():
            for trace_id, rows in group_by_trace(paths, family).items():
                grouped[family][trace_id].extend(rows)
                trace_root_by_id.setdefault(trace_id, trace_root)
    if not args.allow_partial:
        validate_rows(
            grouped,
            trace_root_by_id,
            args.route_vector_availability == "required",
            {stage.strip() for stage in args.stage if stage.strip()},
            args.scenario_pack,
            args.decision_mode,
            args.authority_phase,
        )
    rows = build_rows(
        grouped,
        feedback_root,
        args.authority_mode,
        trace_root_by_id,
        {stage.strip() for stage in args.stage if stage.strip()},
        args.scenario_pack,
        args.decision_mode,
        args.authority_phase,
        args.route_vector_availability,
    )

    append_jsonl(output_dir / "stage_inputs.jsonl", rows["stage_inputs"])
    append_jsonl(output_dir / "stage_outputs.jsonl", rows["stage_outputs"])
    append_jsonl(output_dir / "stage_joins.jsonl", rows["stage_joins"])
    append_jsonl(output_dir / "dispatch_execution.jsonl", rows["dispatch_execution"])
    append_jsonl(output_dir / "dispatch_outcomes.jsonl", rows["dispatch_outcomes"])
    append_jsonl(output_dir / "route_vectors.jsonl", rows["route_vectors"])
    append_jsonl(output_dir / "llm_reasoning_cycles.jsonl", rows["llm_reasoning_cycles"])

    manifest = {
        "schemaVersion": "dispatch-v2-student-dataset-manifest/v1",
        "feedbackRoot": str(feedback_root),
        "discoveredFeedbackRoots": [str(path) for path in trace_roots],
        "authorityMode": args.authority_mode,
        "filters": {
            "stages": [stage for stage in args.stage if stage.strip()],
            "scenarioPack": args.scenario_pack,
            "decisionMode": args.decision_mode,
            "authorityPhase": args.authority_phase,
            "routeVectorAvailability": args.route_vector_availability,
            "allowPartial": args.allow_partial,
        },
        "counts": {name: len(entries) for name, entries in rows.items()},
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
