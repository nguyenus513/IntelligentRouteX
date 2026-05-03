import importlib.util
import io
import json
import time
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
        "decisionMode": "legacy",
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
                "workerAuditPresent": True,
                "workerAuditSource": "ready-state",
                "workerAuditMissingFields": [],
                "applied": True,
                "notAppliedReason": "",
            }
        ],
    }


def benchmark_payload_with_provider_failures(scenario_pack: str) -> dict:
    payload = benchmark_payload(scenario_pack)
    payload["stageFallbackSummary"] = {
        "totalFallbacks": 3,
        "latestFallbackReasonByStage": {
            "ROUTE_GENERATION": "provider-http-error status=500 upstream unavailable",
            "SCENARIO": "provider-timeout after 3000ms",
            "FINAL_SELECTION": "provider-schema-invalid missing selectedPlan",
        },
    }
    return payload


def adaptive_trace_payload(trace_id: str, stage_name: str, worker_name: str, escalated: bool, reason: str) -> dict:
    return {
        "traceId": trace_id,
        "stageName": stage_name,
        "workerName": worker_name,
        "decision": "ESCALATE" if escalated else "SKIP",
        "escalated": escalated,
        "reason": reason,
        "deviceUsed": "cuda" if escalated else "cpu",
        "workerAuditPresent": True,
        "workerAuditSource": "ready-state",
        "workerAuditMissingFields": [],
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

    def test_dry_run_prints_target_stage_and_case_filters(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = validation_runner.main([
                "--dry-run",
                "--mode", "adaptive-only",
                "--target-stage", "bundle-pool",
                "--target-case", "normal-clear/S",
            ])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("target-stages=['bundle-pool']", output)
        self.assertIn("target-cases=['normal-clear/S']", output)
        self.assertIn("case-count=1", output)

    def test_dry_run_route_generation_focus_defaults_cases_and_stage(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = validation_runner.main([
                "--dry-run",
                "--mode", "adaptive-only",
                "--route-generation-focus",
            ])

        output = stdout.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("target-stages=['route-proposal-pool']", output)
        self.assertIn("target-cases=['heavy-rain/S', 'traffic-shock/S']", output)
        self.assertIn("route-generation-focus=True", output)
        self.assertIn("case-count=2", output)

    def test_collects_adaptive_and_comparison_evidence_into_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            comparison_root = temp_root / "comparison"
            output_dir = temp_root / "out"

            for scenario_pack, _ in validation_runner.TARGET_CASES:
                write_json(
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(scenario_pack),
                )
                write_json(
                    comparison_root / f"dispatch-quality-{scenario_pack}-s-legacy-v2-controlled-c-20260423-000002.json",
                    benchmark_payload(scenario_pack, latency_offset_ms=1),
                )
                feedback_root = adaptive_root / "feedback" / scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
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
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
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

    def test_downgrades_verdict_when_worker_audit_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            output_dir = temp_root / "out"

            payload = benchmark_payload("normal-clear")
            payload["workerStatusSnapshot"][0]["workerAuditPresent"] = False
            payload["workerStatusSnapshot"][0]["workerAuditMissingFields"] = ["device"]
            payload["workerStatusSnapshot"][0]["device"] = ""
            write_json(
                adaptive_root / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000001.json",
                payload,
            )
            feedback_root = adaptive_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
            trace = adaptive_trace_payload("trace-normal-clear", "scenario-evaluation", "ml-forecast-worker", False, "worker-device-audit-missing")
            trace["workerAuditPresent"] = False
            trace["workerAuditMissingFields"] = ["device"]
            write_json(feedback_root / "trace-normal-clear.json", trace)

            for scenario_pack, _ in validation_runner.TARGET_CASES[1:]:
                write_json(
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(scenario_pack),
                )
                feedback_root = adaptive_root / "feedback" / scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
                write_json(
                    feedback_root / f"trace-{scenario_pack}.json",
                    adaptive_trace_payload(f"trace-{scenario_pack}", "scenario-evaluation", "ml-forecast-worker", False, "forecast-hot-path-skip"),
                )

            exit_code = validation_runner.main([
                "--adaptive-root", str(adaptive_root),
                "--output-dir", str(output_dir),
                "--mode", "adaptive-only",
            ])

            self.assertEqual(0, exit_code)
            payload = json.loads(next(output_dir.glob("full_adaptive_validation-*.json")).read_text(encoding="utf-8"))
            normal_clear_case = next(case for case in payload["cases"] if case["scenarioPack"] == "normal-clear")
            self.assertEqual("PASS_WITH_LIMITS", normal_clear_case["verdict"])
            self.assertIn("worker-audit-missing:ml-routefinder-worker", normal_clear_case["verdictReasons"])

    def test_rerun_cells_calls_benchmark_runner_for_adaptive_and_comparison_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            calls: List[Tuple[str, str, str]] = []

            def fake_run_validation_cell(cell, out_dir, runner=None):
                calls.append((cell.root_type, cell.scenario_pack, str(out_dir)))
                write_json(
                    out_dir / f"dispatch-quality-{cell.scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(cell.scenario_pack),
                )
                (out_dir / f"dispatch-quality-{cell.scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.md").write_text(
                    "# result",
                    encoding="utf-8",
                )
                if cell.root_type == "adaptive":
                    feedback_root = out_dir / "feedback" / cell.scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
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

    def test_rerun_mode_uses_only_fresh_artifacts_not_stale_root_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            live_adaptive_root = output_dir / "live" / "full-adaptive"
            stale_path = live_adaptive_root / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000000.json"
            write_json(stale_path, benchmark_payload("normal-clear"))

            def fake_run_validation_cell(cell, out_dir, runner=None):
                write_json(
                    out_dir / f"dispatch-quality-{cell.scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(cell.scenario_pack, latency_offset_ms=1),
                )
                (out_dir / f"dispatch-quality-{cell.scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.md").write_text(
                    "# result",
                    encoding="utf-8",
                )
                if cell.root_type == "adaptive":
                    feedback_root = out_dir / "feedback" / cell.scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
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
            payload = json.loads(next(output_dir.glob("full_adaptive_validation-*.json")).read_text(encoding="utf-8"))
            normal_clear_case = next(case for case in payload["cases"] if case["scenarioPack"] == "normal-clear")
            artifact_path = normal_clear_case["adaptive"]["benchmark"]["artifactPath"]
            self.assertTrue(artifact_path.endswith("20260423-000001.json"))
            self.assertNotEqual(str(stale_path), artifact_path)
            self.assertTrue(normal_clear_case["adaptive"]["benchmark"]["artifactLastModifiedAt"])

    def test_root_collection_prefers_latest_benchmark_and_trace_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            output_dir = temp_root / "out"

            stale_benchmark = benchmark_payload("normal-clear")
            stale_benchmark["workerStatusSnapshot"][0]["workerAuditPresent"] = False
            write_json(
                adaptive_root / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000001.json",
                stale_benchmark,
            )
            stale_trace_root = adaptive_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
            stale_trace = adaptive_trace_payload("trace-normal-clear", "scenario-evaluation", "ml-forecast-worker", False, "worker-device-audit-missing")
            stale_trace["workerAuditPresent"] = False
            stale_trace["workerAuditMissingFields"] = ["device"]
            write_json(stale_trace_root / "trace-normal-clear-old.json", stale_trace)

            time.sleep(0.02)

            fresh_benchmark = benchmark_payload("normal-clear")
            write_json(
                adaptive_root / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-999999.json",
                fresh_benchmark,
            )
            fresh_trace = adaptive_trace_payload("trace-normal-clear", "scenario-evaluation", "ml-forecast-worker", True, "")
            write_json(stale_trace_root / "trace-normal-clear-new.json", fresh_trace)

            for scenario_pack, _ in validation_runner.TARGET_CASES[1:]:
                write_json(
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(scenario_pack),
                )
                feedback_root = adaptive_root / "feedback" / scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
                write_json(
                    feedback_root / f"trace-{scenario_pack}.json",
                    adaptive_trace_payload(f"trace-{scenario_pack}", "scenario-evaluation", "ml-forecast-worker", True, ""),
                )

            exit_code = validation_runner.main([
                "--adaptive-root", str(adaptive_root),
                "--output-dir", str(output_dir),
                "--mode", "adaptive-only",
            ])

            self.assertEqual(0, exit_code)
            payload = json.loads(next(output_dir.glob("full_adaptive_validation-*.json")).read_text(encoding="utf-8"))
            normal_clear_case = next(case for case in payload["cases"] if case["scenarioPack"] == "normal-clear")
            self.assertEqual("PASS_WITH_LIMITS", normal_clear_case["verdict"])
            self.assertEqual(["adaptive-skip-not-observed"], normal_clear_case["verdictReasons"])

    def test_route_generation_focus_reports_routefinder_and_provider_classes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            output_dir = temp_root / "out"

            write_json(
                adaptive_root / "dispatch-quality-heavy-rain-s-legacy-v2-controlled-c-20260423-000001.json",
                benchmark_payload_with_provider_failures("heavy-rain"),
            )
            heavy_feedback_root = adaptive_root / "feedback" / "heavy-rain" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
            write_json(
                heavy_feedback_root / "trace-heavy-rain-route.json",
                adaptive_trace_payload("trace-heavy-rain", "route-proposal-pool", "ml-routefinder-worker", False, "routefinder-tuple-budget-exhausted"),
            )

            traffic_payload = benchmark_payload("traffic-shock")
            traffic_payload["routeVectorMetrics"] = {"geometryCoverage": 0.5}
            write_json(
                adaptive_root / "dispatch-quality-traffic-shock-s-legacy-v2-controlled-c-20260423-000001.json",
                traffic_payload,
            )
            traffic_feedback_root = adaptive_root / "feedback" / "traffic-shock" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
            write_json(
                traffic_feedback_root / "trace-traffic-shock-route.json",
                adaptive_trace_payload("trace-traffic-shock", "route-proposal-pool", "ml-routefinder-worker", True, ""),
            )

            exit_code = validation_runner.main([
                "--adaptive-root", str(adaptive_root),
                "--output-dir", str(output_dir),
                "--mode", "adaptive-only",
                "--route-generation-focus",
            ])

            self.assertEqual(0, exit_code)
            payload = json.loads(next(output_dir.glob("targeted_adaptive_closure-route-proposal-pool-*.json")).read_text(encoding="utf-8"))
            self.assertTrue(payload["routeGenerationFocus"])
            heavy_case = next(case for case in payload["cases"] if case["scenarioPack"] == "heavy-rain")
            traffic_case = next(case for case in payload["cases"] if case["scenarioPack"] == "traffic-shock")
            self.assertEqual("http-5xx", heavy_case["routeGenerationFocus"]["routeGenerationProviderFailureClass"])
            self.assertEqual("timeout", heavy_case["adaptive"]["benchmark"]["providerFailureClassesByStage"]["SCENARIO"])
            self.assertEqual(1, heavy_case["routeGenerationFocus"]["routeFinderSkippedCount"])
            self.assertEqual(1, traffic_case["routeGenerationFocus"]["routeFinderEscalatedCount"])
            self.assertEqual("partial", traffic_case["routeGenerationFocus"]["routeVectorAvailability"])

    def test_target_stage_filter_ignores_stale_other_stage_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            adaptive_root = temp_root / "adaptive"
            output_dir = temp_root / "out"

            for scenario_pack, _ in validation_runner.TARGET_CASES:
                write_json(
                    adaptive_root / f"dispatch-quality-{scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(scenario_pack),
                )
                feedback_root = adaptive_root / "feedback" / scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
                write_json(
                    feedback_root / f"trace-{scenario_pack}-bundle.json",
                    adaptive_trace_payload(f"trace-{scenario_pack}", "bundle-pool", "ml-greedrl-worker", False, "greedrl-complexity-below-threshold"),
                )
                stale_route = adaptive_trace_payload(f"trace-{scenario_pack}", "route-proposal-pool", "ml-routefinder-worker", False, "worker-device-audit-missing")
                stale_route["workerAuditPresent"] = False
                stale_route["workerAuditMissingFields"] = ["device"]
                write_json(feedback_root / f"trace-{scenario_pack}-route.json", stale_route)

            exit_code = validation_runner.main([
                "--adaptive-root", str(adaptive_root),
                "--output-dir", str(output_dir),
                "--mode", "adaptive-only",
                "--target-stage", "bundle-pool",
            ])

            self.assertEqual(0, exit_code)
            payload = json.loads(next(output_dir.glob("targeted_adaptive_closure-*.json")).read_text(encoding="utf-8"))
            self.assertEqual(["bundle-pool"], payload["targetStages"])
            self.assertTrue(all(case["verdict"] == "PASS" for case in payload["cases"]))

    def test_targeted_rerun_uses_fresh_stage_root_and_targeted_report_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            calls: List[Tuple[str, str, str]] = []

            def fake_run_validation_cell(cell, out_dir, runner=None):
                calls.append((cell.root_type, cell.scenario_pack, str(out_dir)))
                write_json(
                    out_dir / f"dispatch-quality-{cell.scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.json",
                    benchmark_payload(cell.scenario_pack),
                )
                (out_dir / f"dispatch-quality-{cell.scenario_pack}-s-legacy-v2-controlled-c-20260423-000001.md").write_text(
                    "# result",
                    encoding="utf-8",
                )
                if cell.root_type == "adaptive":
                    feedback_root = out_dir / "feedback" / cell.scenario_pack / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
                    write_json(
                        feedback_root / f"trace-{cell.scenario_pack}.json",
                        adaptive_trace_payload(f"trace-{cell.scenario_pack}", "bundle-pool", "ml-greedrl-worker", False, "greedrl-complexity-below-threshold"),
                    )
                return 0

            original = validation_runner.run_validation_cell
            try:
                validation_runner.run_validation_cell = fake_run_validation_cell
                exit_code = validation_runner.main([
                    "--output-dir", str(output_dir),
                    "--mode", "adaptive-only",
                    "--rerun-cells",
                    "--target-stage", "bundle-pool",
                    "--target-case", "normal-clear/S",
                ])
            finally:
                validation_runner.run_validation_cell = original

            self.assertEqual(0, exit_code)
            self.assertEqual(1, len(calls))
            self.assertIn(str(output_dir / "fresh" / "bundle-pool" / "full-adaptive"), calls[0][2])
            self.assertTrue(next(output_dir.glob("targeted_adaptive_closure-bundle-pool-*.json")).is_file())
            self.assertTrue((output_dir / "targeted_adaptive_closure-bundle-pool_report.md").is_file())

    def test_targeted_rerun_uses_fresh_root_stage_trace_when_latest_delta_misses_target_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"
            fresh_root = output_dir / "fresh" / "bundle-pool" / "full-adaptive"

            write_json(
                fresh_root / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000001.json",
                benchmark_payload("normal-clear"),
            )
            (fresh_root / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000001.md").write_text(
                "# result",
                encoding="utf-8",
            )
            feedback_root = fresh_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-stage" / "adaptive_compute_trace"
            write_json(
                feedback_root / "quality-normal-clear-s-legacy-v2-c-bundle-pool.json",
                adaptive_trace_payload(
                    "trace-normal-clear",
                    "bundle-pool",
                    "ml-greedrl-worker",
                    False,
                    "greedrl-complexity-below-threshold",
                ),
            )

            def fake_run_validation_cell(cell, out_dir, runner=None):
                write_json(
                    out_dir / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000002.json",
                    benchmark_payload("normal-clear", latency_offset_ms=1),
                )
                (out_dir / "dispatch-quality-normal-clear-s-legacy-v2-controlled-c-20260423-000002.md").write_text(
                    "# result",
                    encoding="utf-8",
                )
                write_json(
                    feedback_root / "quality-normal-clear-s-legacy-v2-c-scenario-evaluation.json",
                    adaptive_trace_payload(
                        "trace-normal-clear",
                        "scenario-evaluation",
                        "ml-forecast-worker",
                        False,
                        "scenario-not-demanding",
                    ),
                )
                return 0

            original = validation_runner.run_validation_cell
            try:
                validation_runner.run_validation_cell = fake_run_validation_cell
                exit_code = validation_runner.main([
                    "--output-dir", str(output_dir),
                    "--mode", "adaptive-only",
                    "--rerun-cells",
                    "--target-stage", "bundle-pool",
                    "--target-case", "normal-clear/S",
                ])
            finally:
                validation_runner.run_validation_cell = original

            self.assertEqual(0, exit_code)
            payload = json.loads(next(output_dir.glob("targeted_adaptive_closure-bundle-pool-*.json")).read_text(encoding="utf-8"))
            self.assertEqual("PASS", payload["cases"][0]["verdict"])
            self.assertIn("target-stage-policy-observed", payload["cases"][0]["verdictReasons"])
            self.assertEqual(1, payload["cases"][0]["adaptive"]["adaptiveTrace"]["totalAdaptiveDecisions"])

    def test_rerun_mode_fails_when_cell_emits_no_fresh_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "out"

            def fake_run_validation_cell(cell, out_dir, runner=None):
                return 0

            original = validation_runner.run_validation_cell
            try:
                validation_runner.run_validation_cell = fake_run_validation_cell
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = validation_runner.main([
                        "--output-dir", str(output_dir),
                        "--mode", "adaptive-only",
                        "--rerun-cells",
                    ])
            finally:
                validation_runner.run_validation_cell = original

            output = stdout.getvalue()
            self.assertEqual(1, exit_code)
            self.assertIn("completed without fresh benchmark JSON artifacts", output)


if __name__ == "__main__":
    unittest.main()
