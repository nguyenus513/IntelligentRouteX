import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List, Tuple


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_full_adaptive_validation.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_full_adaptive_validation", MODULE_PATH)
validation_runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validation_runner
SPEC.loader.exec_module(validation_runner)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def benchmark_payload(scenario_pack: str, prompt_family: str = "v2", latency_offset_ms: int = 0) -> dict:
    return {
        "baselineId": "C",
        "scenarioPack": scenario_pack,
        "workloadSize": "S",
        "decisionMode": "llm-authoritative",
        "promptFamily": prompt_family,
        "executionMode": "controlled",
        "cellStartedAt": "2026-04-23T00:00:00Z",
        "dispatchCompletedAt": f"2026-04-23T00:00:0{1 + latency_offset_ms}Z",
        "mlAttachStatus": "ATTACHED",
        "timeoutPhase": "NONE",
        "metrics": {
            "selectedProposalCount": 1,
            "executedAssignmentCount": 1,
            "robustUtilityAverage": 0.62,
            "selectorObjectiveValue": 1.0,
            "workerFallbackRate": 0.0,
        },
        "routeVectorMetrics": {"geometryCoverage": 1.0},
        "stageFallbackSummary": {"totalFallbacks": 0},
        "workerStatusSnapshot": [
            {
                "workerName": "ml-routefinder-worker",
                "enabled": True,
                "ready": True,
                "device": "cuda",
                "dtype": "fp16",
                "gpuMemoryAllocatedMb": 512,
                "batchSize": 4,
                "compileMode": "default",
                "modelLoaded": True,
                "warmupDone": True,
                "applied": True,
                "notAppliedReason": "",
            }
        ],
    }


def adaptive_trace_payload(trace_id: str, stage_name: str, worker_name: str, escalated: bool, reason: str) -> dict:
    return {
        "traceId": trace_id,
        "stageName": stage_name,
        "workerName": worker_name,
        "decision": "ESCALATE" if escalated else "SKIP",
        "escalated": escalated,
        "reason": reason,
        "deviceUsed": "cuda" if escalated else "cpu",
    }


class RunDispatchFullAdaptiveValidationTest(unittest.TestCase):
    def test_dry_run_prints_adaptive_and_comparison_cells(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = validation_runner.main(["--dry-run", "--mode", "paired"])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("[FULL ADAPTIVE VALIDATION] case-count=8", output)
        self.assertIn("root-type=adaptive scenario-pack=normal-clear", output)
        self.assertIn("root-type=comparison scenario-pack=forecast-heavy", output)

    def test_collects_adaptive_and_comparison_evidence_into_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            comparison_root = temp_root / "comparison"
            output_dir = temp_root / "out"

            for scenario_pack, _ in validation_runner.TARGET_CASES:
                write_json(
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-llm-authoritative-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(scenario_pack),
                )
                write_json(
                    comparison_root / f"dispatch-quality-{scenario_pack}-s-llm-authoritative-v2-controlled-c-20260423-000002.json",
                    benchmark_payload(scenario_pack, latency_offset_ms=1),
                )
                feedback_root = adaptive_root / "feedback" / scenario_pack / "s" / "controlled" / "llm-authoritative" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
                write_json(
                    feedback_root / f"trace-{scenario_pack}-route-proposal-pool.json",
                    adaptive_trace_payload(f"trace-{scenario_pack}", "route-proposal-pool", "ml-routefinder-worker", False, "routefinder-not-needed"),
                )
                write_json(
                    feedback_root / f"trace-{scenario_pack}-scenario-evaluation.json",
                    adaptive_trace_payload(f"trace-{scenario_pack}", "scenario-evaluation", "ml-forecast-worker", True, "forecast-needed"),
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = validation_runner.main([
                    "--adaptive-root", str(adaptive_root),
                    "--comparison-root", str(comparison_root),
                    "--output-dir", str(output_dir),
                    "--mode", "paired",
                ])

            self.assertEqual(0, exit_code)
            report_path = output_dir / "full_adaptive_validation_report.md"
            self.assertTrue(report_path.is_file())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("`normal-clear`", report)
            self.assertIn("`PASS`", report)
            json_reports = sorted(output_dir.glob("full_adaptive_validation-*.json"))
            self.assertEqual(1, len(json_reports))
            payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
            self.assertEqual(4, len(payload["cases"]))
            self.assertTrue(all(case["verdict"] == "PASS" for case in payload["cases"]))

    def test_reports_evidence_gap_when_adaptive_trace_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            output_dir = temp_root / "out"

            for scenario_pack, _ in validation_runner.TARGET_CASES:
                write_json(
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-llm-authoritative-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(scenario_pack),
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = validation_runner.main([
                    "--adaptive-root", str(adaptive_root),
                    "--output-dir", str(output_dir),
                    "--mode", "adaptive-only",
                ])

            self.assertEqual(0, exit_code)
            payload = json.loads(next(output_dir.glob("full_adaptive_validation-*.json")).read_text(encoding="utf-8"))
            self.assertTrue(all(case["verdict"] == "EVIDENCE_GAP" for case in payload["cases"]))

    def test_rerun_cells_calls_benchmark_runner_for_adaptive_and_comparison_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            calls: List[Tuple[str, str, str]] = []

            def fake_run_validation_cell(cell, out_dir, runner=None):
                calls.append((cell.root_type, cell.scenario_pack, str(out_dir)))
                write_json(
                    out_dir / f"dispatch-quality-{cell.scenario_pack}-s-llm-authoritative-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(cell.scenario_pack),
                )
                if cell.root_type == "adaptive":
                    feedback_root = out_dir / "feedback" / cell.scenario_pack / "s" / "controlled" / "llm-authoritative" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
                    write_json(
                        feedback_root / f"trace-{cell.scenario_pack}.json",
                        adaptive_trace_payload(f"trace-{cell.scenario_pack}", "route-proposal-pool", "ml-routefinder-worker", False, "routefinder-not-needed"),
                    )
                return 0

            original = validation_runner.run_validation_cell
            try:
                validation_runner.run_validation_cell = fake_run_validation_cell
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = validation_runner.main([
                        "--output-dir", str(output_dir),
                        "--mode", "paired",
                        "--rerun-cells",
                    ])
            finally:
                validation_runner.run_validation_cell = original

            self.assertEqual(0, exit_code)
            self.assertEqual(8, len(calls))
            self.assertEqual({"adaptive", "comparison"}, {call[0] for call in calls})
            self.assertTrue((output_dir / "full_adaptive_validation_report.md").is_file())


if __name__ == "__main__":
    unittest.main()
