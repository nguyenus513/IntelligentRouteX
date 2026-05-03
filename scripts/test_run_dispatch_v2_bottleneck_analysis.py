import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "run_dispatch_v2_bottleneck_analysis.py"
SPEC = importlib.util.spec_from_file_location("run_dispatch_v2_bottleneck_analysis", MODULE_PATH)
bottleneck = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = bottleneck
SPEC.loader.exec_module(bottleneck)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class BottleneckAnalysisRunnerTest(unittest.TestCase):
    def test_smoke_matrix_plans_single_standard_step(self) -> None:
        steps = bottleneck.planned_steps("smoke", Path("out"))

        self.assertEqual(1, len(steps))
        self.assertEqual("standard-smoke-full-adaptive", steps[0].name)
        self.assertIn("run_dispatch_v2_standard_comparison.py", " ".join(steps[0].command))
        self.assertIn("full-adaptive", steps[0].command)

    def test_deep_matrix_omits_llm_steps_by_policy(self) -> None:
        steps = bottleneck.planned_steps("deep", Path("out"))

        self.assertFalse(any("llm" in step.name for step in steps))
        self.assertFalse(any("llm-gated" in step.command for step in steps))

    def test_collects_standard_rows_and_ranks_stage_latency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_json(root / "standard_comparison-1.json", {
                "cells": [{
                    "scenarioPack": "normal-clear",
                    "size": "S",
                    "profile": "full-adaptive",
                    "stageLatencies": {"route-proposal-pool": 4000, "scenario-evaluation": 200},
                    "mlInvocations": {"routefinder-local": {"latencyMs": 56}},
                    "routeProposalCount": 1000,
                    "routeGeometryCoverage": 0.8,
                    "robustUtilityAverage": 0.75,
                    "executedAssignmentCount": 16,
                    "verdict": "PASS_WITH_LIMITS",
                    "verdictReasons": ["route-generation:route-vector-coverage-below-1.0"],
                }]
            })

            rows = bottleneck.standard_rows(root)
            rank = bottleneck.stage_latency_rank(rows)
            route = bottleneck.route_generation_breakdown(rows)

            self.assertEqual(1, len(rows))
            self.assertEqual("route-proposal-pool", rank[0]["name"])
            self.assertEqual(4000, route[0]["routeStageLatencyMs"])
            self.assertEqual(56, route[0]["routeFinderLatencyMs"])

    def test_classifies_route_generation_when_route_stage_dominates_but_routefinder_is_small(self) -> None:
        rows = [{
            "scenarioPack": "traffic-shock",
            "size": "S",
            "profile": "full-adaptive",
            "stageLatencies": {"route-proposal-pool": 5000, "scenario-evaluation": 500},
            "mlInvocations": {"routefinder-local": {"latencyMs": 56}},
            "verdictReasons": [],
        }]

        verdict = bottleneck.classify_bottleneck(rows, [], {"missingAuditCount": 0})

        self.assertEqual("ROUTE_GENERATION", verdict["primary"])

    def test_keeps_geo_source_secondary_when_route_runtime_dominates(self) -> None:
        rows = [{
            "scenarioPack": "heavy-rain",
            "size": "S",
            "profile": "full-adaptive",
            "stageLatencies": {"route-proposal-pool": 5000, "scenario-evaluation": 500},
            "mlInvocations": {"routefinder-local": {"latencyMs": 56}},
            "verdictReasons": [
                "tomtom-disabled",
                "open-meteo-top-level-disabled",
                "route-generation:route-vector-coverage-below-1.0",
            ],
        }]

        verdict = bottleneck.classify_bottleneck(rows, [], {"missingAuditCount": 0})

        self.assertEqual("ROUTE_GENERATION", verdict["primary"])
        self.assertIn("GEO_SOURCE", verdict["secondary"])

    def test_classifies_llm_provider_when_request_meta_has_provider_error(self) -> None:
        verdict = bottleneck.classify_bottleneck(
            [],
            [{"fallbackReason": "provider-http-error", "details": {"exceptionClass": "java.net.http.HttpTimeoutException"}}],
            {"missingAuditCount": 0},
        )

        self.assertEqual("LLM_PROVIDER", verdict["primary"])

    def test_write_reports_emits_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = {
                "schemaVersion": "dispatch-v2-bottleneck-analysis/v1",
                "generatedAt": "2026-04-24T00:00:00Z",
                "gitCommit": "test",
                "matrix": "smoke",
                "sourceCounts": {"standardRows": 1},
                "bottleneckVerdict": {"primary": "ROUTE_GENERATION", "secondary": [], "scores": {}},
                "stageLatencyRank": [{"name": "route-proposal-pool", "totalLatencyMs": 4000}],
                "mlLatencyRank": [],
                "llmLatencyRank": [],
                "routeGenerationBreakdown": [{
                    "cell": "normal-clear/S/full-adaptive",
                    "proposalCount": 256,
                    "routeStageLatencyMs": 799,
                    "geometryCoverage": 1.0,
                    "executedAssignmentCount": 16,
                }],
                "fallbackBreakdown": [],
                "qualityVsCost": [],
            }

            json_path, markdown_path = bottleneck.write_reports(payload, Path(temp_dir))

            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("ROUTE_GENERATION", markdown)
            self.assertIn("## Final Verdict", markdown)
            self.assertIn("candidate explosion", markdown)
            self.assertIn("RouteFinder inference is not the primary runtime bottleneck", markdown)


if __name__ == "__main__":
    unittest.main()
