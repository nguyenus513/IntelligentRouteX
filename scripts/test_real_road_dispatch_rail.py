import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_module(name: str, filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


metrics_module = load_module("build_real_road_metrics", "build_real_road_metrics.py")
gate_module = load_module("evaluate_real_road_loop_gate", "evaluate_real_road_loop_gate.py")
rail_module = load_module("run_real_road_dispatch_rail", "run_real_road_dispatch_rail.py")


class RealRoadDispatchRailTest(unittest.TestCase):
    def test_loop_one_gate_passes_road_native_metrics(self) -> None:
        verdict, reasons = gate_module.gate_loop(1, {
            "snapSuccessRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "syntheticFallbackRouteCount": 0,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("PASS", verdict)
        self.assertIn("loop-01-road-route-evidence-pass", reasons)

    def test_loop_one_gate_fails_straight_line_selected_route(self) -> None:
        verdict, reasons = gate_module.gate_loop(1, {
            "snapSuccessRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 1,
            "selectedRoutePolylineCoverage": 0.8,
            "syntheticFallbackRouteCount": 0,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("FAIL", verdict)
        self.assertIn("selected-route-rendered-as-straight-line", reasons)

    def test_loop_two_gate_requires_road_aware_generation(self) -> None:
        verdict, reasons = gate_module.gate_loop(2, {
            "geoGenerationMode": "road-aware",
            "snapSuccessRate": 1.0,
            "routableOrderRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "badGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "syntheticFallbackRouteCount": 0,
            "coveredOrderCount": 20,
            "baselineCoveredOrderCount": 20,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("PASS", verdict)
        self.assertIn("loop-02-road-aware-generator-pass", reasons)

    def test_loop_two_gate_fails_legacy_generation(self) -> None:
        verdict, reasons = gate_module.gate_loop(2, {
            "geoGenerationMode": "legacy-synthetic",
            "snapSuccessRate": 1.0,
            "routableOrderRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "badGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "coveredOrderCount": 20,
            "baselineCoveredOrderCount": 20,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("FAIL", verdict)
        self.assertIn("geo-generation-mode-not-road-aware", reasons)

    def test_loop_three_gate_requires_matrix_coverage(self) -> None:
        verdict, reasons = gate_module.gate_loop(3, {
            "snapSuccessRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "syntheticFallbackRouteCount": 0,
            "selectedRouteMatrixCoverage": 1.0,
            "matrixFallbackRate": 0.0,
            "matrixPointCount": 45,
            "matrixPairCount": 2025,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("PASS", verdict)
        self.assertIn("loop-03-osrm-table-matrix-cache-pass", reasons)

    def test_loop_three_gate_fails_missing_matrix_pairs(self) -> None:
        verdict, reasons = gate_module.gate_loop(3, {
            "snapSuccessRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "selectedRouteMatrixCoverage": 0.2,
            "matrixFallbackRate": 0.0,
            "matrixPointCount": 0,
            "matrixPairCount": 0,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("FAIL", verdict)
        self.assertIn("selected-route-matrix-coverage-below-0.95", reasons)
        self.assertIn("matrix-point-count-missing", reasons)

    def test_loop_four_gate_requires_valid_pickup_dropoff_sequence(self) -> None:
        verdict, reasons = gate_module.gate_loop(4, {
            "snapSuccessRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "syntheticFallbackRouteCount": 0,
            "pickupBeforeDropoffValid": True,
            "evaluatedSequenceCount": 1260,
            "coveredOrderCount": 20,
            "baselineCoveredOrderCount": 20,
            "selectedSingleOrderCount": 0,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("PASS", verdict)
        self.assertIn("loop-04-road-native-sequence-optimizer-pass", reasons)

    def test_loop_four_gate_fails_invalid_stop_order(self) -> None:
        verdict, reasons = gate_module.gate_loop(4, {
            "snapSuccessRate": 1.0,
            "roadRouteCoverage": 1.0,
            "selectedBadGeoPointCount": 0,
            "visualStraightLineSelectedRouteCount": 0,
            "selectedRoutePolylineCoverage": 1.0,
            "pickupBeforeDropoffValid": False,
            "evaluatedSequenceCount": 20,
            "coveredOrderCount": 20,
            "baselineCoveredOrderCount": 20,
            "selectedSingleOrderCount": 0,
            "executedAssignmentCount": 5,
        }, provider_ready=True)

        self.assertEqual("FAIL", verdict)
        self.assertIn("pickup-before-dropoff-invalid", reasons)

    def test_build_metrics_counts_visual_road_polylines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            benchmark_root = root / "benchmark"
            visual_root = root / "visual"
            artifact_path = benchmark_root / "dispatch-quality.json"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text(json.dumps({
                "metrics": {"executedAssignmentCount": 1, "coveredOrderCount": 2},
                "routeVectorMetrics": {"proposalCount": 2, "geometryCoverage": 1.0},
                "routeProposalBudgetMetrics": {},
                "stageLatencies": {"route-proposal-pool": 123},
                "degradeReasons": [],
            }), encoding="utf-8")
            (benchmark_root / "standard_comparison-1.json").write_text(json.dumps({
                "cells": [{"artifactPath": str(artifact_path)}]
            }), encoding="utf-8")
            visual_root.mkdir(parents=True)
            (visual_root / "dispatch_visual_evidence.json").write_text(json.dumps({
                "cells": [{
                    "visualRoadSnapEvidence": {"requestedPointCount": 2, "snappedPointCount": 2, "maxSnapDistanceMeters": 10},
                    "selectedRoutes": [{
                        "path": [
                            {"kind": "osrm-road-overlay", "lat": 1, "lon": 1},
                            {"kind": "osrm-road-overlay", "lat": 1.1, "lon": 1.1},
                            {"kind": "osrm-road-overlay", "lat": 1.2, "lon": 1.2},
                        ],
                        "roadOverlay": {"status": "ready", "provider": "osrm-routing", "fallbackCount": 0},
                        "shapeAnalysis": {"verdict": "GOOD", "detourRatio": 1.1},
                        "travelTimeSeconds": 50,
                    }],
                }]
            }), encoding="utf-8")

            metrics = metrics_module.build_metrics(benchmark_root, visual_root)

            self.assertEqual(1.0, metrics["snapSuccessRate"])
            self.assertEqual(1.0, metrics["roadRouteCoverage"])
            self.assertEqual(0, metrics["visualStraightLineSelectedRouteCount"])
            self.assertEqual(1.0, metrics["selectedRoutePolylineCoverage"])

    def test_build_metrics_validates_pickup_before_dropoff_from_leg_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            benchmark_root = root / "benchmark"
            visual_root = root / "visual"
            artifact_path = benchmark_root / "dispatch-quality.json"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text(json.dumps({
                "scenarioPack": "dense-bundle-20x5",
                "metrics": {"executedAssignmentCount": 1, "coveredOrderCount": 2, "selectedSingleOrderCount": 0},
                "routeVectorMetrics": {"proposalCount": 1, "geometryCoverage": 1.0},
                "routeProposalBudgetMetrics": {"routeVectorComputedCount": 1, "routeVectorReusedCount": 0},
                "degradeReasons": [],
            }), encoding="utf-8")
            (benchmark_root / "standard_comparison-1.json").write_text(json.dumps({
                "cells": [{"artifactPath": str(artifact_path)}]
            }), encoding="utf-8")
            visual_root.mkdir(parents=True)
            (visual_root / "dispatch_visual_evidence.json").write_text(json.dumps({
                "cells": [{
                    "visualRoadSnapEvidence": {"requestedPointCount": 4, "snappedPointCount": 4, "maxSnapDistanceMeters": 5},
                    "selectedRoutes": [{
                        "orderIds": ["order-1", "order-2"],
                        "benchmarkPath": [
                            {"id": "driver-1", "kind": "driver"},
                            {"id": "order-1:pickup->order-2:pickup:0", "kind": "synthetic-straight-line"},
                            {"id": "order-2:pickup->order-1:dropoff:0", "kind": "synthetic-straight-line"},
                            {"id": "order-1:dropoff->order-2:dropoff:0", "kind": "synthetic-straight-line"},
                        ],
                        "path": [{"kind": "osrm-road-overlay"}, {"kind": "osrm-road-overlay"}, {"kind": "osrm-road-overlay"}],
                        "roadOverlay": {"status": "ready", "provider": "osrm-routing", "fallbackCount": 0},
                        "shapeAnalysis": {"verdict": "GOOD", "detourRatio": 1.0},
                    }],
                }]
            }), encoding="utf-8")

            metrics = metrics_module.build_metrics(benchmark_root, visual_root)

            self.assertTrue(metrics["pickupBeforeDropoffValid"])
            self.assertEqual(1, metrics["pickupBeforeDropoffValidRouteCount"])

    def test_unimplemented_loop_writes_evidence_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            loop_dir = Path(temp_dir) / "loop-05"
            loop_dir.mkdir(parents=True)
            manifest = loop_dir / "loop_manifest.json"
            manifest.write_text(json.dumps({"loop": 5}), encoding="utf-8")

            verdict, reasons = rail_module.run_unimplemented_loop(loop_dir, 5, manifest)

            self.assertEqual("EVIDENCE_GAP", verdict)
            self.assertTrue((loop_dir / "metrics.json").exists())
            self.assertTrue((loop_dir / "routePlanQualityLoopReport.md").exists())
            self.assertIn("loop-05-road-route-quality-classifier-implementation-not-yet-wired", reasons)


if __name__ == "__main__":
    unittest.main()
