import json
import tempfile
import unittest
from pathlib import Path

import build_route_quality_report as route_quality


def artifact(scenario="normal-clear", geometry=1.0, path_efficiency=0.85, dominance=0.99, fallback=0, selected=3, executed=3):
    return {
        "scenarioPack": scenario,
        "workloadSize": "M",
        "baselineId": "A",
        "metrics": {
            "selectedProposalCount": selected,
            "executedAssignmentCount": executed,
            "coveredOrderCount": selected * 2,
            "executionValid": True,
            "conflictFreeAssignments": True,
            "routeFallbackRate": 0.0,
            "workerFallbackRate": 0.0,
            "selectorObjectiveValue": 3.0,
        },
        "routeVectorMetrics": {
            "geometryCoverage": geometry,
            "averagePathEfficiency": path_efficiency,
            "averageStraightnessScore": path_efficiency,
            "routeDominanceRate": dominance,
        },
        "objectiveTelemetry": {
            "selectedTotalUtility": float(selected),
            "selectedRiskCost": 0.0,
            "selectedQualityCost": 0.0,
            "selectedReward": 0.0,
        },
        "selectorTelemetry": {"timedOut": False, "selectorPoolCapObjectiveLoss": 0.0},
        "bundleDiversity": {"familyDiversityCount": 3},
        "stageFallbackSummary": {"totalFallbacks": fallback},
    }


class BuildRouteQualityReportTest(unittest.TestCase):
    def test_passes_clean_route_quality_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-normal-clear-m-legacy-v2-controlled-a.json").write_text(json.dumps(artifact()), encoding="utf-8")
            report = route_quality.summarize(route_quality.load_rows(root), 0.70, ["normal-clear"])

        self.assertTrue(report["pass"])
        self.assertFalse(report["badRows"])
        self.assertGreaterEqual(report["minQualityScore"], 0.70)

    def test_blocks_low_geometry_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-normal-clear-m-legacy-v2-controlled-a.json").write_text(
                json.dumps(artifact(geometry=0.25, path_efficiency=0.30, dominance=0.50)),
                encoding="utf-8",
            )
            report = route_quality.summarize(route_quality.load_rows(root), 0.70, ["normal-clear"])

        self.assertFalse(report["pass"])
        self.assertIn("geometry-coverage-low", report["blockerCounts"])
        self.assertIn("path-efficiency-low", report["blockerCounts"])

    def test_low_dominance_is_scored_but_not_a_hard_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-dense-bundle-20x5-m-legacy-v2-controlled-a.json").write_text(
                json.dumps(artifact("dense-bundle-20x5", dominance=0.25)),
                encoding="utf-8",
            )
            report = route_quality.summarize(route_quality.load_rows(root), 0.70, ["dense-bundle-20x5"])

        self.assertTrue(report["pass"])
        self.assertLess(report["minQualityScore"], 1.0)

    def test_blocks_fallback_or_unexecuted_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-traffic-shock-m-legacy-v2-controlled-a.json").write_text(
                json.dumps(artifact("traffic-shock", fallback=1, selected=2, executed=0)),
                encoding="utf-8",
            )
            report = route_quality.summarize(route_quality.load_rows(root), 0.70, ["traffic-shock"])

        self.assertFalse(report["pass"])
        self.assertIn("fallback-used", report["blockerCounts"])
        self.assertIn("no-executed-assignment", report["blockerCounts"])

    def test_worker_fallback_is_not_route_quality_blocker(self) -> None:
        payload = artifact("worker-degradation")
        payload["metrics"]["workerFallbackRate"] = 0.75
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "dispatch-quality-worker-degradation-m-legacy-v2-controlled-a.json").write_text(json.dumps(payload), encoding="utf-8")
            report = route_quality.summarize(route_quality.load_rows(root), 0.70, ["worker-degradation"])

        self.assertTrue(report["pass"])
        self.assertNotIn("fallback-used", report["blockerCounts"])


if __name__ == "__main__":
    unittest.main()
