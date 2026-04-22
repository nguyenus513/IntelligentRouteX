import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_module(name: str, filename: str):
    module_path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate_logs = load_module("validate_distillation_logs", "validate_distillation_logs.py")
silver_builder = load_module("build_silver_from_bronze", "build_silver_from_bronze.py")
gold_builder = load_module("build_gold_distillation_datasets", "build_gold_distillation_datasets.py")
smoke_report = load_module("write_harvest_smoke_report", "write_harvest_smoke_report.py")


class DispatchV2HarvestPipelineTest(unittest.TestCase):
    def test_bronze_to_gold_pipeline_builds_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bronze_root = Path(temp_dir) / "bronze"
            silver_root = Path(temp_dir) / "silver"
            gold_root = Path(temp_dir) / "gold"
            report_path = Path(temp_dir) / "artifacts" / "harvest" / "harvest_smoke_report.md"
            families = (
                "harvest-run-manifest",
                "decision-stage-input",
                "decision-stage-output",
                "decision-stage-join",
                "dispatch-execution",
                "dispatch-outcome",
                "geo-tile-selection-trace",
                "tile-feature-trace",
                "bundle-geometry-trace",
                "driver-pickup-fit-trace",
                "route-vector-trace",
                "route-stop-trace",
                "traffic-context-trace",
                "tabular-teacher-trace",
                "greedrl-teacher-trace",
                "routefinder-teacher-trace",
                "forecast-teacher-trace",
            )
            for family in families:
                (bronze_root / family).mkdir(parents=True, exist_ok=True)

            run_id = "trace-1"

            def write_row(family: str, row: dict) -> None:
                target = bronze_root / family / f"{run_id}.jsonl"
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row) + "\n")

            candidate_base = {
                "traceId": run_id,
                "runId": run_id,
                "tickId": "tick-1",
                "stageName": "pair-bundle",
                "entityType": "bundle",
                "entityId": "bundle-1",
                "candidateId": "bundle:bundle-1",
                "observationTime": "2026-04-23T00:00:00Z",
                "timeLayer": "observation",
                "antiLeakageClass": "DECISION_SAFE",
                "source": "measured",
                "fallbackUsed": False,
                "missingReason": "",
                "pickupLat": 10.0,
                "pickupLng": 106.0,
                "dropLat": 10.1,
                "dropLng": 106.1,
                "bundleCentroidLat": 10.05,
                "bundleCentroidLng": 106.05,
            }
            write_row("harvest-run-manifest", {
                "schemaVersion": "harvest-run-manifest/v1",
                "rowType": "stage",
                "timeLayer": "teacher",
                "antiLeakageClass": "METADATA_ONLY",
                "traceId": run_id,
                "runId": run_id,
                "tickId": "tick-1",
                "stageName": "dispatch-run",
                "entityType": "run",
                "entityId": run_id,
                "decisionTime": "2026-04-23T00:00:00Z",
            })
            write_row("decision-stage-input", {
                "schemaVersion": "bronze-candidate-row/v1",
                "rowType": "candidate",
                **candidate_base,
                "score": 0.7,
            })
            write_row("decision-stage-output", {
                "schemaVersion": "bronze-candidate-row/v1",
                "rowType": "candidate",
                **{k: v for k, v in candidate_base.items() if k != "observationTime"},
                "decisionTime": "2026-04-23T00:00:00Z",
                "timeLayer": "teacher",
                "antiLeakageClass": "TEACHER_DECISION",
                "score": 0.9,
                "confidence": 0.8,
                "selected": True,
            })
            write_row("decision-stage-join", {
                "schemaVersion": "bronze-candidate-row/v1",
                "rowType": "candidate",
                **{k: v for k, v in candidate_base.items() if k != "observationTime"},
                "decisionTime": "2026-04-23T00:00:00Z",
                "timeLayer": "teacher",
                "antiLeakageClass": "TEACHER_DECISION",
                "selected": True,
                "downstreamChosen": True,
            })
            write_row("dispatch-execution", {
                "schemaVersion": "dispatch-execution-bronze/v1",
                "rowType": "stage",
                "timeLayer": "teacher",
                "antiLeakageClass": "TEACHER_DECISION",
                "traceId": run_id,
                "runId": run_id,
                "tickId": "tick-1",
                "stageName": "dispatch-executor",
                "entityType": "execution",
                "entityId": run_id,
                "decisionTime": "2026-04-23T00:00:00Z",
                "source": "dispatch-executor",
                "fallbackUsed": False,
                "missingReason": "",
            })
            write_row("dispatch-outcome", {
                "schemaVersion": "dispatch-outcome-bronze/v1",
                "rowType": "outcome",
                "timeLayer": "outcome",
                "antiLeakageClass": "OUTCOME_ONLY",
                "traceId": run_id,
                "runId": run_id,
                "tickId": "tick-1",
                "stageName": "dispatch-outcome",
                "entityType": "outcome",
                "entityId": run_id,
                "outcomeTime": "2026-04-23T00:05:00Z",
                "source": "simulated-outcome",
                "fallbackUsed": False,
                "missingReason": "",
                "labelQuality": "SIMULATED_STRONG",
                "delivered": True,
            })
            write_row("geo-tile-selection-trace", {
                "schemaVersion": "geo-tile-selection-trace/v1",
                "rowType": "candidate",
                **candidate_base,
                "tileId": "tile-1",
                "tileSource": "selector",
            })
            write_row("tile-feature-trace", {
                "schemaVersion": "tile-feature-trace/v1",
                "rowType": "candidate",
                **candidate_base,
                "majorRoadRatio": 0.6,
                "tileSource": "encoder",
            })
            write_row("bundle-geometry-trace", {
                "schemaVersion": "bundle-geometry-trace/v1",
                "rowType": "candidate",
                **candidate_base,
                "routeSpreadMeters": 300.0,
            })
            write_row("driver-pickup-fit-trace", {
                "schemaVersion": "driver-pickup-fit-trace/v1",
                "rowType": "candidate",
                **candidate_base,
                "driverLat": 10.2,
                "driverLng": 106.2,
                "driverToFirstPickupDistanceMeters": 180.0,
            })
            write_row("route-vector-trace", {
                "schemaVersion": "route-vector-trace/v1",
                "rowType": "summary",
                "traceId": run_id,
                "runId": run_id,
                "tickId": "tick-1",
                "stageName": "pair-bundle",
                "entityType": "bundle",
                "entityId": "bundle-1",
                "candidateId": "bundle:bundle-1",
                "observationTime": "2026-04-23T00:00:00Z",
                "timeLayer": "observation",
                "antiLeakageClass": "DECISION_SAFE",
                "source": "route-vector-summary",
                "fallbackUsed": False,
                "missingReason": "",
                "proposalId": "proposal-1",
                "routeDistanceMeters": 800.0,
            })
            write_row("route-stop-trace", {
                "schemaVersion": "route-stop-trace/v1",
                "rowType": "candidate",
                "traceId": run_id,
                "runId": run_id,
                "tickId": "tick-1",
                "stageName": "pair-bundle",
                "entityType": "bundle",
                "entityId": "bundle-1",
                "candidateId": "bundle:bundle-1",
                "observationTime": "2026-04-23T00:00:00Z",
                "timeLayer": "observation",
                "antiLeakageClass": "DECISION_SAFE",
                "source": "route-stop-projection",
                "fallbackUsed": False,
                "missingReason": "",
                "proposalId": "proposal-1",
                "orderId": "order-1",
                "stopType": "pickup",
                "stopIndex": 0,
                "lat": 10.0,
                "lng": 106.0,
                "legDistanceMeters": 200.0,
                "legTravelTimeSeconds": 90.0,
            })
            write_row("traffic-context-trace", {
                "schemaVersion": "traffic-context-trace/v1",
                "rowType": "candidate",
                **candidate_base,
                "avgSpeedMps": 6.0,
                "trafficSource": "simulated",
                "weatherSource": "simulated",
            })
            for family, teacher_kind in (
                ("tabular-teacher-trace", "tabular"),
                ("greedrl-teacher-trace", "greedrl"),
                ("routefinder-teacher-trace", "routefinder"),
                ("forecast-teacher-trace", "forecast"),
            ):
                write_row(family, {
                    "schemaVersion": f"{family}/v1",
                    "rowType": "candidate",
                    "traceId": run_id,
                    "runId": run_id,
                    "tickId": "tick-1",
                    "stageName": "pair-bundle",
                    "entityType": "bundle",
                    "entityId": "bundle-1",
                    "candidateId": "bundle:bundle-1",
                    "decisionTime": "2026-04-23T00:00:00Z",
                    "timeLayer": "teacher",
                    "antiLeakageClass": "TEACHER_DECISION",
                    "source": "teacher-worker",
                    "fallbackUsed": False,
                    "missingReason": "",
                    "teacherKind": teacher_kind,
                    "applied": True,
                })

            validate_result = validate_logs.validate(bronze_root)
            self.assertGreater(validate_result["candidateRows"], 0)
            (bronze_root / "validation_report.json").write_text(json.dumps(validate_result), encoding="utf-8")

            silver_exit = silver_builder.main(["--bronze-root", str(bronze_root), "--output-dir", str(silver_root)])
            self.assertEqual(0, silver_exit)
            self.assertTrue((silver_root / "decision_stage_join_canonical.jsonl").is_file())

            gold_exit = gold_builder.main(["--silver-root", str(silver_root), "--output-dir", str(gold_root)])
            self.assertEqual(0, gold_exit)
            self.assertTrue((gold_root / "unified_dispatch_distillation.parquet").is_file())
            self.assertTrue((gold_root / "selection_score.parquet").is_file())

            smoke_exit = smoke_report.main([
                "--bronze-root", str(bronze_root),
                "--silver-root", str(silver_root),
                "--gold-root", str(gold_root),
                "--output", str(report_path),
            ])
            self.assertEqual(0, smoke_exit)
            self.assertTrue(report_path.is_file())
            self.assertIn("Harvest Smoke Report", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
