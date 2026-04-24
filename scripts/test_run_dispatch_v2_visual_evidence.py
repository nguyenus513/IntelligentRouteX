import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_visual_evidence.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_visual_evidence", MODULE_PATH)
visual = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = visual
SPEC.loader.exec_module(visual)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class DispatchVisualEvidenceTest(unittest.TestCase):
    def test_builds_visual_payload_from_replay_and_reuse_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "live" / "full-adaptive" / "normal-clear" / "s"
            artifact_path = output_root / "dispatch-quality.json"
            write_json(root / "standard_comparison-1.json", {
                "gitCommit": "test",
                "cells": [{
                    "scenarioPack": "normal-clear",
                    "size": "S",
                    "profile": "full-adaptive",
                    "artifactPath": str(artifact_path),
                    "outputRoot": str(output_root),
                }],
            })
            write_json(artifact_path, {
                "metrics": {"executedAssignmentCount": 1, "robustUtilityAverage": 0.8},
                "routeVectorMetrics": {"proposalCount": 2, "geometryCoverage": 1.0},
                "stageLatencies": {"route-proposal-pool": 123},
                "routeProposalBudgetMetrics": {"budgetMode": "full-adaptive-s"},
                "degradeReasons": [],
            })
            write_json(output_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "replay" / "quality.json", {
                "request": {
                    "traceId": "trace-1",
                    "weatherProfile": "CLEAR",
                    "openOrders": [{
                        "orderId": "order-1",
                        "pickupPoint": {"latitude": 10.1, "longitude": 106.1},
                        "dropoffPoint": {"latitude": 10.2, "longitude": 106.2},
                    }],
                    "availableDrivers": [{
                        "driverId": "driver-1",
                        "currentLocation": {"latitude": 10.0, "longitude": 106.0},
                    }],
                },
            })
            write_json(output_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "reuse-states" / "quality-reuse-state.json", {
                "routeProposals": [{
                    "proposalId": "proposal-1",
                    "bundleId": "bundle-1",
                    "driverId": "driver-1",
                    "source": "HEURISTIC_SAFE",
                    "stopOrder": ["order-1"],
                    "routeValue": 0.9,
                    "projectedPickupEtaMinutes": 2.0,
                    "projectedCompletionEtaMinutes": 8.0,
                    "totalDistanceMeters": 1200,
                    "totalTravelTimeSeconds": 400,
                    "routeCost": 500,
                    "congestionScore": 0.3,
                    "turnCount": 2,
                    "reasons": ["safe-support-priority"],
                    "degradeReasons": [],
                }],
            })
            write_json(output_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c" / "decision-log" / "quality.json", {
                "selectedProposalIds": ["proposal-1"],
                "executedAssignmentIds": ["proposal-1|driver-1|1"],
            })

            payload = visual.build_payload(root, ("normal-clear",), ("full-adaptive",), "S")
            html = visual.render_html(payload, max_routes=4)

            self.assertEqual("dispatch-v2-visual-evidence/v1", payload["schemaVersion"])
            self.assertEqual(1, len(payload["cells"]))
            self.assertEqual(1, payload["cells"][0]["selectedProposalCount"])
            self.assertIn("Visual evidence", html)
            self.assertIn("driver-1", html)
            self.assertIn("pickup", html)
            self.assertIn("Global selector", html)


if __name__ == "__main__":
    unittest.main()
