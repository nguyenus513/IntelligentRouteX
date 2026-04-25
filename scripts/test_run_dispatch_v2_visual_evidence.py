import importlib.util
import json
import sys
import tempfile
import unittest
import base64
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


def write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="))


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
            self.assertIn("Play realtime turn", html)
            self.assertIn("data-step='orders'", html)
            self.assertIn("data-playback-step", html)
            self.assertIn("driver-triangle", html)
            self.assertIn("driver-radius", html)
            self.assertIn("Route text", html)
            self.assertIn("System chooses", html)
            self.assertIn("driver-1", html)
            self.assertIn("pickup", html)
            self.assertIn("Global selector", html)

    def test_tile_probe_evidence_is_copied_and_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "live" / "full-adaptive" / "normal-clear" / "s"
            artifact_path = output_root / "dispatch-quality.json"
            tile_root = root / "tiles"
            osm_cache = tile_root / "cache" / "osm-raster" / "14" / "13045" / "7740.png"
            tomtom_cache = tile_root / "cache" / "tomtom-raster-basic" / "14" / "13045" / "7740.png"
            write_png(osm_cache)
            write_png(tomtom_cache)
            write_json(tile_root / "geo_tile_probe.json", {
                "schemaVersion": "dispatch-v2-geo-tile-probe/v1",
                "generatedAt": "2026-04-25T00:00:00+00:00",
                "center": {"lat": 10.7769, "lon": 106.7009},
                "zoom": 14,
                "tile": {"z": 14, "x": 13045, "y": 7740},
                "providers": ["osm", "tomtom"],
                "tiles": [{
                    "provider": "osm-raster",
                    "tile": {"z": 14, "x": 13045, "y": 7740},
                    "urlTemplate": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    "status": "FETCHED",
                    "httpStatus": 200,
                    "byteCount": 68,
                    "cachePath": str(osm_cache),
                    "cacheHit": False,
                    "latencyMs": 12,
                    "degradeReason": "",
                    "attribution": "OpenStreetMap contributors",
                }, {
                    "provider": "tomtom-raster-basic",
                    "tile": {"z": 14, "x": 13045, "y": 7740},
                    "urlTemplate": "https://api.tomtom.com/map/1/tile/basic/main/{z}/{x}/{y}.png?key=secret",
                    "status": "CACHE_HIT",
                    "httpStatus": 200,
                    "byteCount": 68,
                    "cachePath": str(tomtom_cache),
                    "cacheHit": True,
                    "latencyMs": 1,
                    "degradeReason": "",
                    "attribution": "TomTom",
                }],
            })
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
                "stageLatencies": {},
                "routeProposalBudgetMetrics": {},
                "degradeReasons": [],
            })
            base = output_root / "feedback" / "normal-clear" / "s" / "controlled" / "legacy" / "v2" / "c"
            write_json(base / "replay" / "quality.json", {"request": {"openOrders": [], "availableDrivers": []}})
            write_json(base / "reuse-states" / "quality-reuse-state.json", {"routeProposals": []})
            write_json(base / "decision-log" / "quality.json", {"selectedProposalIds": [], "executedAssignmentIds": []})

            payload = visual.build_payload(root, ("normal-clear",), ("full-adaptive",), "S", tile_probe_root=tile_root)
            report_root = root / "visual"
            visual.write_reports(payload, report_root, max_routes=4)
            html = (report_root / "dispatch_visual_evidence.html").read_text(encoding="utf-8")

            self.assertEqual("available", payload["tileEvidence"]["status"])
            self.assertIn("key=<redacted>", payload["tileEvidence"]["tiles"][1]["urlTemplate"])
            self.assertTrue((report_root / "tiles" / "osm-raster" / "14" / "13045" / "7740.png").exists())
            self.assertIn("Tile source status: available", html)
            self.assertIn("osm-raster", html)
            self.assertIn("tomtom-raster-basic", html)
            self.assertIn("tiles/osm-raster/14/13045/7740.png", html)

    def test_single_turn_limits_payload_to_first_matching_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = []
            for scenario in ("normal-clear", "heavy-rain"):
                output_root = root / "live" / "full-adaptive" / scenario / "s"
                artifact_path = output_root / "dispatch-quality.json"
                rows.append({
                    "scenarioPack": scenario,
                    "size": "S",
                    "profile": "full-adaptive",
                    "artifactPath": str(artifact_path),
                    "outputRoot": str(output_root),
                })
                write_json(artifact_path, {
                    "metrics": {"executedAssignmentCount": 1, "robustUtilityAverage": 0.8},
                    "routeVectorMetrics": {"proposalCount": 2, "geometryCoverage": 1.0},
                    "stageLatencies": {},
                    "routeProposalBudgetMetrics": {},
                    "degradeReasons": [],
                })
                base = output_root / "feedback" / scenario / "s" / "controlled" / "legacy" / "v2" / "c"
                write_json(base / "replay" / "quality.json", {"request": {"openOrders": [], "availableDrivers": []}})
                write_json(base / "reuse-states" / "quality-reuse-state.json", {"routeProposals": []})
                write_json(base / "decision-log" / "quality.json", {"selectedProposalIds": [], "executedAssignmentIds": []})
            write_json(root / "standard_comparison-1.json", {"gitCommit": "test", "cells": rows})

            payload = visual.build_payload(root, (), ("full-adaptive",), "S", single_turn=True)

            self.assertEqual(1, len(payload["cells"]))
            self.assertEqual("normal-clear", payload["cells"][0]["scenario"])


if __name__ == "__main__":
    unittest.main()
