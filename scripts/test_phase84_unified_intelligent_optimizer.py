from __future__ import annotations

from pathlib import Path

from optimizer.phase84_adaptive_budget import AdaptiveBudgetController
from optimizer.phase84_feature_extractor import InstanceFeatureExtractor
from optimizer.phase84_hyper_heuristic import AdaptiveHyperHeuristic
from optimizer.phase84_route_pool_memory import RoutePoolMemory
from optimizer.phase84_route_set_selector import AdaptiveRouteSetSelector
from optimizer.phase84_unified_objective import UnifiedNaturalObjective
from run_phase84_antihardcode_guard import scan
from run_phase84_benchmark_victory_guard import evaluate


def instance() -> dict:
    return {
        "schemaVersion": "external-benchmark-normalized/v1",
        "problemType": "PDPTW",
        "instanceName": "unit-anything",
        "depotNodeId": "0",
        "vehicleCount": 1,
        "capacity": 2,
        "nodes": [
            {"id": "0", "x": 0, "y": 0, "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 0},
            {"id": "1", "x": 1, "y": 0, "readyTime": 0, "dueTime": 50, "serviceTime": 0, "demand": 1},
            {"id": "2", "x": 2, "y": 0, "readyTime": 0, "dueTime": 80, "serviceTime": 0, "demand": -1},
        ],
        "requests": [{"orderId": "r1", "pickupNodeId": "1", "dropoffNodeId": "2", "demand": 1}],
        "distanceMatrix": [[0, 1, 2], [1, 0, 1], [2, 1, 0]],
        "durationMatrix": [[0, 1, 2], [1, 0, 1], [2, 1, 0]],
        "activeRoutes": [],
        "drivers": [],
    }


def feasible_solution() -> dict:
    return {"routes": [["0", "1", "2", "0"]]}


def test_feature_extractor_does_not_depend_on_instance_name() -> None:
    left = instance()
    right = {**instance(), "instanceName": "another-name"}

    assert InstanceFeatureExtractor().extract(left).to_dict() == InstanceFeatureExtractor().extract(right).to_dict()


def test_objective_rejects_hard_violations() -> None:
    bad = {"routes": [["0", "2", "1", "0"]]}

    assert UnifiedNaturalObjective().evaluate(instance(), bad)["feasible"] is False


def test_adaptive_budget_deterministic() -> None:
    features = InstanceFeatureExtractor().extract(instance()).to_dict()
    controller = AdaptiveBudgetController()

    assert controller.allocate(1000, features, ["traffic-aware-insertion", "route-elimination"]) == controller.allocate(1000, features, ["traffic-aware-insertion", "route-elimination"])


def test_operator_scoring_deterministic() -> None:
    heuristic = AdaptiveHyperHeuristic()
    features = InstanceFeatureExtractor().extract(instance()).to_dict()

    assert heuristic.select(["b", "a"], features) == "a"


def test_route_pool_rejects_non_internal_provenance() -> None:
    pool = RoutePoolMemory()

    assert pool.add_route(instance(), ["0", "1", "2", "0"], "test", provenance="external") is False


def test_route_set_selector_exact_covers_requests() -> None:
    pool = RoutePoolMemory()
    pool.add_route(instance(), ["0", "1", "2", "0"], "test")

    selected = AdaptiveRouteSetSelector().select(instance(), feasible_solution(), pool)

    assert selected["routes"] == feasible_solution()["routes"]


def test_traffic_low_confidence_penalizes_tight_routes() -> None:
    features = InstanceFeatureExtractor().extract({**instance(), "trafficContext": {"confidence": 0.2, "multiplier": 2.0}}).to_dict()
    budgets = AdaptiveBudgetController().allocate(1000, features, ["traffic-aware-insertion", "route-elimination"])

    assert budgets["traffic-aware-insertion"].allocatedMs > budgets["route-elimination"].allocatedMs


def test_antihardcode_guard_catches_startswith_lrc(tmp_path: Path) -> None:
    root = tmp_path / "optimizer"
    root.mkdir()
    (root / "bad.py").write_text("name.startswith(\"LRC\")", encoding="utf-8")

    assert scan(root)["gate"] == "FAIL"


def test_promotion_guard_rejects_safety_regression() -> None:
    report = evaluate({"aggregate": {"hardViolations": 1, "overBudget": 0, "fallback": 0, "vroomWins": 0}, "antiHardcodeGate": "PASS"})

    assert report["gate"] == "FAIL"


def test_no_production_main_ready_claim() -> None:
    text = Path("docs/benchmark/phase84_unified_intelligent_optimizer_report.md").read_text(encoding="utf-8") + Path("docs/benchmark/phase84_remaining_weaknesses.md").read_text(encoding="utf-8")

    assert "does not claim `PRODUCTION_MAIN_READY`" in text or "not `PRODUCTION_MAIN_READY`" in text
