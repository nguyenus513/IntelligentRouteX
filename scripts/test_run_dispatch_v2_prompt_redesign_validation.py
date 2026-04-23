import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List, Tuple


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_prompt_redesign_validation.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_prompt_redesign_validation", MODULE_PATH)
validation_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validation_runner
SPEC.loader.exec_module(validation_runner)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def prompt_trace_payload(trace_id: str, stage: str, prompt_family: str, checksum_suffix: str, richness: float = 1.0) -> dict:
    return {
        "traceId": trace_id,
        "stageName": stage,
        "promptFamily": prompt_family,
        "promptSpecVersion": "decision-stage-prompt-spec/v3" if prompt_family == "v3" else "decision-stage-prompt-spec/v1",
        "stagePromptName": stage,
        "stagePromptChecksum": f"{prompt_family}-{checksum_suffix}-prompt",
        "packetTemplateVersion": "decision-stage-packet/v3" if prompt_family == "v3" else "decision-stage-packet/v2",
        "packetTemplateChecksum": f"{prompt_family}-{checksum_suffix}-packet",
        "candidateCountSeen": 12,
        "comparisonPackCoverage": 1.0,
        "geospatialCoverage": 1.0,
        "missingContextFlags": [],
        "visibilityProfile": f"{stage}-visibility-v1",
        "comparisonLens": "PAIR_SUPPORT_LENS",
        "geospatialLens": "BUNDLE_GEOMETRY_LENS",
        "skillSetVersion": "decision-stage-skill-set/v1" if prompt_family == "v3" else "",
        "skillIdsActivated": ["vector_compare"] if prompt_family == "v3" else [],
        "sessionStoreEnabled": prompt_family == "v3",
        "sessionNamespace": "run-1/tick-1/trace-2" if prompt_family == "v3" else "",
        "sessionReadRefs": ["stage:route-generation"] if prompt_family == "v3" else [],
        "sessionWriteRefs": ["selected-candidate:bundle-1"] if prompt_family == "v3" else [],
        "sessionRefCount": 1 if prompt_family == "v3" else 0,
        "fallbackReason": "",
        "richnessHint": richness,
    }


class PromptRedesignValidationTest(unittest.TestCase):
    def test_dry_run_prints_planned_cells_for_both_families(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = validation_runner.main(["--dry-run", "--stage", "pair-bundle", "--prompt-family", "both"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("[PROMPT VALIDATION] stage-count=2", output)
        self.assertIn("stage=pair-bundle prompt-family=v2", output)
        self.assertIn("stage=pair-bundle prompt-family=v3", output)

    def test_collects_paired_v2_v3_evidence_into_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            baseline_root = temp_root / "baseline"
            validation_root = temp_root / "validation"
            output_dir = temp_root / "out"

            benchmark_v2 = {
                "baselineId": "C",
                "scenarioPack": "normal-clear",
                "workloadSize": "S",
                "decisionMode": "llm-shadow",
                "promptFamily": "v2",
                "executionMode": "controlled",
                "runAuthorityClass": "LOCAL_NON_AUTHORITY",
                "authorityEligible": False,
                "tokenUsageSummary": {"totalTokens": 100},
                "stageFallbackSummary": {"totalFallbacks": 0},
            }
            benchmark_v3 = dict(benchmark_v2, promptFamily="v3")
            write_json(baseline_root / "dispatch-quality-normal-clear-s-llm-shadow-v2-controlled-c-20260423-000000.json", benchmark_v2)
            write_json(validation_root / "dispatch-quality-normal-clear-s-llm-shadow-v2-controlled-c-20260423-000001.json", benchmark_v2)
            write_json(validation_root / "dispatch-quality-normal-clear-s-llm-shadow-v3-controlled-c-20260423-000002.json", benchmark_v3)

            base_feedback = baseline_root / "feedback" / "normal-clear" / "s" / "controlled" / "llm-shadow" / "v2" / "c" / "decision-stage"
            validation_feedback_v2 = validation_root / "feedback" / "normal-clear" / "s" / "controlled" / "llm-shadow" / "v2" / "c" / "decision-stage"
            validation_feedback_v3 = validation_root / "feedback" / "normal-clear" / "s" / "controlled" / "llm-shadow" / "v3" / "c" / "decision-stage"

            write_json(base_feedback / "llm_prompt_spec_trace" / "trace-1-pair-bundle.json", prompt_trace_payload("trace-1", "pair-bundle", "v2", "base"))
            write_json(
                base_feedback / "decision_stage_output" / "trace-1-pair-bundle.json",
                {
                    "traceId": "trace-1",
                    "stageName": "PAIR_BUNDLE",
                    "brainType": "LLM",
                    "assessments": {"summary": "old", "items": [{"id": "bundle-1", "score": 0.7, "selected": True, "rationale": "old"}]},
                    "meta": {"fallbackUsed": False},
                },
            )
            write_json(base_feedback / "decision_stage_join" / "trace-1-pair-bundle.json", {"traceId": "trace-1", "stageName": "PAIR_BUNDLE", "selectedIds": ["bundle-1"], "rejectedIds": ["bundle-2"]})

            for prompt_family, feedback_root, rich_items in (
                ("v2", validation_feedback_v2, [
                    {"id": "bundle-1", "score": 0.8, "rank": 1, "selected": True, "confidence": 0.9, "reasonCodes": ["fit"], "dominanceReasonCodes": [], "regretToBestAlternative": 0.1, "driverFitSummary": "n/a", "routeVectorRefs": [], "geospatialFlags": ["compact"], "burstSensitivityFlags": [], "rationale": "best"},
                    {"id": "bundle-2", "score": 0.7, "rank": 2, "selected": False, "confidence": 0.7, "reasonCodes": ["spread"], "dominanceReasonCodes": ["dominated"], "regretToBestAlternative": 0.2, "driverFitSummary": "n/a", "routeVectorRefs": [], "geospatialFlags": ["wide"], "burstSensitivityFlags": [], "rationale": "worse"},
                ]),
                ("v3", validation_feedback_v3, [
                    {"id": "bundle-1", "score": 0.82, "rank": 1, "selected": True, "confidence": 0.92, "reasonCodes": ["fit"], "dominanceReasonCodes": [], "regretToBestAlternative": 0.08, "driverFitSummary": "strong", "routeVectorRefs": ["proposal-1"], "geospatialFlags": ["compact"], "burstSensitivityFlags": [], "rationale": "best", "extra": "ignored"},
                    {"id": "bundle-2", "score": 0.68, "rank": 2, "selected": False, "confidence": 0.69, "reasonCodes": ["spread"], "dominanceReasonCodes": ["dominated"], "regretToBestAlternative": 0.22, "driverFitSummary": "ok", "routeVectorRefs": ["proposal-2"], "geospatialFlags": ["wide"], "burstSensitivityFlags": ["burst"], "rationale": "worse"},
                ]),
            ):
                write_json(
                    feedback_root / "llm_prompt_spec_trace" / f"trace-{prompt_family}-pair-bundle.json",
                    prompt_trace_payload(f"trace-{prompt_family}", "pair-bundle", prompt_family, "commit"),
                )
                write_json(
                    feedback_root / "llm_skill_activation_trace" / f"trace-{prompt_family}-pair-bundle.json",
                    {
                        "traceId": f"trace-{prompt_family}",
                        "stageName": "pair-bundle",
                        "promptFamily": prompt_family,
                        "skillSetVersion": "decision-stage-skill-set/v1" if prompt_family == "v3" else "",
                        "skillIdsActivated": ["vector_compare"] if prompt_family == "v3" else [],
                        "sessionStoreEnabled": prompt_family == "v3",
                        "sessionNamespace": "run-1/tick-1/trace-v3" if prompt_family == "v3" else "",
                        "sessionReadRefs": ["stage:route-generation"] if prompt_family == "v3" else [],
                        "sessionWriteRefs": [],
                        "sessionRefCount": 1 if prompt_family == "v3" else 0,
                    },
                )
                write_json(
                    feedback_root / "decision_session_stage_summary" / f"trace-{prompt_family}-pair-bundle.json",
                    {
                        "traceId": f"trace-{prompt_family}",
                        "stageName": "pair-bundle",
                        "sessionNamespace": "run-1/tick-1/trace-v3" if prompt_family == "v3" else "",
                        "sessionWriteRefs": ["selected-candidate:bundle-1"] if prompt_family == "v3" else [],
                    },
                )
                write_json(
                    feedback_root / "decision_stage_output" / f"trace-{prompt_family}-pair-bundle.json",
                    {
                        "traceId": f"trace-{prompt_family}",
                        "stageName": "PAIR_BUNDLE",
                        "brainType": "LLM",
                        "assessments": {"summary": "new", "reasonCodes": ["ok"], "items": rich_items},
                        "meta": {"fallbackUsed": False},
                    },
                )
                write_json(
                    feedback_root / "decision_stage_join" / f"trace-{prompt_family}-pair-bundle.json",
                    {"traceId": f"trace-{prompt_family}", "stageName": "PAIR_BUNDLE", "selectedIds": ["bundle-1"], "rejectedIds": ["bundle-2"]},
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = validation_runner.main([
                    "--baseline-root", str(baseline_root),
                    "--validation-root", str(validation_root),
                    "--output-dir", str(output_dir),
                    "--stage", "pair-bundle",
                    "--prompt-family", "both",
                ])

            self.assertEqual(0, exit_code)
            report_path = output_dir / "prompt_redesign_validation_report.md"
            self.assertTrue(report_path.is_file())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("`pair-bundle`", report)
            self.assertIn("`IDENTITY_ONLY`", report)
            json_reports = sorted(output_dir.glob("prompt-redesign-validation-*.json"))
            self.assertEqual(1, len(json_reports))
            payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
            family_reports = payload["stageReports"][0]["familyReports"]
            self.assertEqual("PASS", family_reports["v2"]["overallVerdict"])
            self.assertEqual("PASS", family_reports["v3"]["overallVerdict"])
            self.assertEqual("IDENTITY_ONLY", payload["stageReports"][0]["pairedComparison"]["verdict"])
            self.assertEqual(1, family_reports["v2"]["validationEvidenceCount"])
            self.assertEqual(1, family_reports["v3"]["validationEvidenceCount"])

    def test_rerun_cells_calls_benchmark_runner_for_each_family(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            calls: List[Tuple[str, str, str]] = []

            def fake_run_validation_cell(cell, out_dir, runner=None):
                calls.append((cell.stage, cell.prompt_family, str(out_dir)))
                write_json(
                    out_dir / f"dispatch-quality-{cell.scenario_pack}-{cell.size.lower()}-{cell.decision_mode}-{cell.prompt_family}-controlled-c-20260423-000000.json",
                    {
                        "baselineId": cell.baseline,
                        "scenarioPack": cell.scenario_pack,
                        "workloadSize": cell.size,
                        "decisionMode": cell.decision_mode,
                        "promptFamily": cell.prompt_family,
                        "executionMode": cell.execution_mode,
                        "runAuthorityClass": "LOCAL_NON_AUTHORITY",
                        "authorityEligible": False,
                        "tokenUsageSummary": {"totalTokens": 10},
                        "stageFallbackSummary": {"totalFallbacks": 0},
                    },
                )
                feedback_root = out_dir / "feedback" / cell.scenario_pack / cell.size.lower() / cell.execution_mode / cell.decision_mode / cell.prompt_family / "c" / "decision-stage"
                write_json(
                    feedback_root / "llm_prompt_spec_trace" / f"trace-{cell.prompt_family}-{cell.stage}.json",
                    prompt_trace_payload(f"trace-{cell.prompt_family}-{cell.stage}", cell.stage, cell.prompt_family, cell.stage),
                )
                write_json(
                    feedback_root / "decision_stage_output" / f"trace-{cell.prompt_family}-{cell.stage}.json",
                    {
                        "traceId": f"trace-{cell.prompt_family}-{cell.stage}",
                        "stageName": cell.stage.replace("-", "_").upper(),
                        "brainType": "LLM",
                        "assessments": {
                            "summary": "ok",
                            "items": [
                                {"id": "a", "score": 0.8, "rank": 1, "selected": True, "confidence": 0.8, "reasonCodes": [], "dominanceReasonCodes": [], "regretToBestAlternative": 0.0, "driverFitSummary": "ok", "routeVectorRefs": [], "geospatialFlags": [], "burstSensitivityFlags": [], "rationale": "ok"},
                                {"id": "b", "score": 0.7, "rank": 2, "selected": False, "confidence": 0.7, "reasonCodes": [], "dominanceReasonCodes": [], "regretToBestAlternative": 0.1, "driverFitSummary": "ok", "routeVectorRefs": [], "geospatialFlags": [], "burstSensitivityFlags": [], "rationale": "ok"},
                            ],
                        },
                        "meta": {"fallbackUsed": False},
                    },
                )
                write_json(feedback_root / "decision_stage_join" / f"trace-{cell.prompt_family}-{cell.stage}.json", {"traceId": f"trace-{cell.prompt_family}-{cell.stage}", "stageName": cell.stage.replace("-", "_").upper(), "selectedIds": ["a"], "rejectedIds": ["b"]})
                return 0

            original_run_validation_cell = validation_runner.run_validation_cell
            try:
                validation_runner.run_validation_cell = fake_run_validation_cell
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = validation_runner.main([
                        "--output-dir", str(output_dir),
                        "--stage", "pair-bundle",
                        "--prompt-family", "both",
                        "--rerun-cells",
                    ])
            finally:
                validation_runner.run_validation_cell = original_run_validation_cell

            self.assertEqual(0, exit_code)
            self.assertEqual(2, len(calls))
            self.assertEqual({"v2", "v3"}, {call[1] for call in calls})
            self.assertTrue((output_dir / "prompt_redesign_validation_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
