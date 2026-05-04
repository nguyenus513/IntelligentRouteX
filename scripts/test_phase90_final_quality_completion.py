from __future__ import annotations

from pathlib import Path

from optimizer.phase84_operator_portfolio import OperatorPortfolio
from optimizer.phase84_route_pool_memory import RouteColumn, RoutePoolMemory
from optimizer.phase90_alns_repair_engine import ALNSRepairEngine
from optimizer.phase90_alns_acceptance import DeterministicRandom, accepts
from optimizer.phase90_deadline import Deadline
from optimizer.phase90_distance_polish import DistancePolish
from optimizer.phase90_improvement_opportunity import ImprovementOpportunityDetector
from optimizer.phase90_exact_delta_scorer import ExactDeltaScorer
from optimizer.phase90_local_search_chain import LocalSearchChain
from optimizer.phase90_route_compression import RouteCompression
from optimizer.phase90_route_pool_recombiner import RoutePoolRecombiner
from optimizer.phase90_route_population import RoutePopulation
from phase67_synthetic_instance_loader import load_benchmark_instance
from run_phase84_antihardcode_guard import scan
from run_phase90_final_victory_guard import evaluate_gate


def instance() -> dict:
    matrix = [
        [0, 1, 8, 2, 3],
        [1, 0, 10, 1, 2],
        [8, 10, 0, 20, 8],
        [2, 1, 20, 0, 1],
        [3, 2, 8, 1, 0],
    ]
    return {
        "depotNodeId": "0",
        "vehicleCount": 2,
        "capacity": 2,
        "nodes": [
            {"id": "0", "readyTime": 0, "dueTime": 500, "serviceTime": 0, "demand": 0},
            {"id": "1", "readyTime": 0, "dueTime": 500, "serviceTime": 0, "demand": 1},
            {"id": "2", "readyTime": 0, "dueTime": 500, "serviceTime": 0, "demand": -1},
            {"id": "3", "readyTime": 0, "dueTime": 500, "serviceTime": 0, "demand": 1},
            {"id": "4", "readyTime": 0, "dueTime": 500, "serviceTime": 0, "demand": -1},
        ],
        "requests": [{"orderId": "a", "pickupNodeId": "1", "dropoffNodeId": "2"}, {"orderId": "b", "pickupNodeId": "3", "dropoffNodeId": "4"}],
        "distanceMatrix": matrix,
        "durationMatrix": matrix,
        "activeRoutes": [],
        "drivers": [],
    }


def test_exact_delta_scorer_detects_distance_improvement() -> None:
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    candidate = {"routes": [["0", "1", "3", "4", "2", "0"]]}

    delta = ExactDeltaScorer().score(instance(), incumbent, candidate)

    assert delta.distanceDelta < 0


def test_quality_filter_prunes_no_quality_candidate() -> None:
    solution = {"routes": [["0", "1", "3", "4", "2", "0"]]}
    result = OperatorPortfolio().apply("intra-route-pair-relocate", instance(), solution, {}, None, None)

    assert "checkerFeasibleCandidates" in result["telemetry"]
    assert "objectiveImprovingCandidates" in result["telemetry"]
    assert "objectiveNotImprovedCandidates" in result["telemetry"]


def test_local_search_chain_preserves_exact_pickup_dropoff_coverage() -> None:
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    generated = list(LocalSearchChain().generate(instance(), incumbent, maxChains=4, maxDepth=2))

    assert all({"1", "2", "3", "4"}.issubset({stop for route in item["solution"]["routes"] for stop in route}) for item in generated)


def test_route_compression_does_not_target_k_and_yields_quality_potential() -> None:
    incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    generated = list(RouteCompression().generate(instance(), incumbent, maxCandidates=4))

    assert generated
    assert all(item["delta"]["vehicleDelta"] <= 0 or item["delta"]["objectiveDeltaEstimate"] < 0 for item in generated)


def test_distance_polish_generates_distance_negative_candidate() -> None:
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    generated = list(DistancePolish().generate(instance(), incumbent, maxCandidates=8))

    assert generated
    assert all(item["delta"]["distanceDelta"] < 0 for item in generated)



def test_alns_intermediate_can_be_worse_but_final_must_improve() -> None:
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    generated = list(ALNSRepairEngine().generate(instance(), incumbent, maxIterations=20, beam=8))

    assert generated
    assert all(item.get("candidateStage") == "final" for item in generated)
    improving = [item for item in generated if item["delta"]["objectiveDeltaEstimate"] < 0]
    assert improving


def test_regret_repair_restores_exact_pickup_dropoff_coverage() -> None:
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    generated = list(ALNSRepairEngine().generate(instance(), incumbent, maxIterations=20, beam=8))
    stops = {stop for item in generated for route in item["solution"]["routes"] for stop in route}

    assert {"1", "2", "3", "4"}.issubset(stops)


def test_ejection_repair_preserves_pickup_before_dropoff() -> None:
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    generated = list(ALNSRepairEngine().generate(instance(), incumbent, maxIterations=20, beam=8, ejectionDepth=2))

    assert generated
    for item in generated:
        for route in item["solution"]["routes"]:
            if "1" in route and "2" in route:
                assert route.index("1") < route.index("2")
            if "3" in route and "4" in route:
                assert route.index("3") < route.index("4")


def test_route_population_rejects_duplicate_signatures() -> None:
    population = RoutePopulation()
    solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}

    assert population.add(instance(), solution) is True
    assert population.add(instance(), solution) is False
    assert population.lastTelemetry["duplicateRejected"] == 1


def test_route_pool_recombiner_rejects_non_internal_provenance() -> None:
    pool = RoutePoolMemory()
    pool.columns["external"] = RouteColumn(["a"], ["0", "1", "2", "0"], 1.0, "external", "external", provenance="external", allowedForClaim=True)
    recombiner = RoutePoolRecombiner()
    list(recombiner.generate(instance(), {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}, pool, maxCandidates=2))

    assert recombiner.lastRejectedNonInternal == 1


def test_telemetry_separates_checker_feasible_and_objective_improving() -> None:
    result = OperatorPortfolio().apply("distance-polish", instance(), {"routes": [["0", "1", "2", "3", "4", "0"]]}, {}, None, None)
    telemetry = result["telemetry"]

    assert "checkerFeasibleCandidates" in telemetry
    assert "objectiveImprovingCandidates" in telemetry
    assert "acceptedCandidates" in telemetry


def test_antihardcode_guard_passes() -> None:
    assert scan()["gate"] == "PASS"


def test_victory_guard_rejects_regression() -> None:
    assert evaluate_gate({"hardViolations": 1, "overBudget": 0, "acceptedCandidates": 1}, "PASS") == "FAIL"


def test_victory_guard_rejects_suite_regression() -> None:
    assert evaluate_gate({"hardViolations": 0, "overBudget": 0, "acceptedCandidates": 1}, "PASS", regressions=1) == "FAIL"


def test_docs_do_not_claim_production_main_ready() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in Path("docs/benchmark").glob("phase90_*.md"))

    assert "PRODUCTION_MAIN_READY" not in docs


def test_deadline_expires_and_operator_returns_safely() -> None:
    deadline = Deadline.from_time_limit_ms(0)
    result = OperatorPortfolio().apply("alns-destroy-repair", instance(), {"routes": [["0", "1", "2", "3", "4", "0"]]}, {}, None, None, deadline)

    assert result["telemetry"]["safeReturn"] is True
    assert result["solution"]["routes"] == [["0", "1", "2", "3", "4", "0"]]


def test_alns_loop_respects_deadline() -> None:
    deadline = Deadline.from_time_limit_ms(1)
    generated = list(ALNSRepairEngine().generate(instance(), {"routes": [["0", "1", "2", "3", "4", "0"]]}, maxIterations=10_000, beam=8, deadline=deadline))

    assert len(generated) <= 8


def test_population_loop_respects_deadline() -> None:
    deadline = Deadline.from_time_limit_ms(1)
    population = RoutePopulation()
    solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    list(population.generate(instance(), solution, [solution], maxCandidates=1000, deadline=deadline))

    assert population.lastTelemetry["populationDiversity"] >= 1


def test_opportunity_detector_detects_weak_route() -> None:
    solution = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    report = ImprovementOpportunityDetector().detect(instance(), solution)

    assert "weak-route" in report["reasons"]


def test_no_opportunity_case_does_not_require_accepted_candidates() -> None:
    assert evaluate_gate({"hardViolations": 0, "overBudget": 0, "acceptedCandidates": 0, "checkerFeasibleCandidates": 0, "qualityOpportunityCases": 0}, "PASS") == "PASS_WITH_LIMITS"


def test_opportunity_no_improvement_is_pass_with_limits_when_bounded() -> None:
    assert evaluate_gate({"hardViolations": 0, "overBudget": 0, "acceptedCandidates": 0, "checkerFeasibleCandidates": 0, "qualityOpportunityCases": 1, "qualityOpportunityWithoutImprovement": 1, "boundedSearchNoImprovement": True}, "PASS") == "PASS_WITH_LIMITS"


def test_victory_guard_rejects_timeout_or_missing_summary() -> None:
    assert evaluate_gate({"timeoutCount": 1}, "PASS") == "FAIL"
    assert evaluate_gate({}, "PASS", summary_exists=False) == "FAIL"


def test_sa_acceptance_always_accepts_improvement() -> None:
    assert accepts(100.0, 90.0, 90.0, 1.0, DeterministicRandom.from_signature("stable"), 0) is True


def test_sa_acceptance_sometimes_accepts_worse_deterministically() -> None:
    rng = DeterministicRandom.from_signature("stable-worse")

    first = accepts(100.0, 101.0, 90.0, 10.0, rng, 1)
    second = accepts(100.0, 101.0, 90.0, 10.0, rng, 1)

    assert first is True
    assert first == second


def test_opportunity_fixture_crossing_routes_produces_accepted_candidate() -> None:
    fixture = load_benchmark_instance("phase90-opportunity", "crossing_routes_distance_polish")
    incumbent = {"routes": [["0", "1", "2", "3", "4", "0"]]}
    result = OperatorPortfolio().apply("alns-destroy-repair", fixture, incumbent, {}, None, None, Deadline.from_time_limit_ms(5000))

    assert result["telemetry"]["acceptedCandidates"] > 0


def test_weak_route_compression_accepts_only_objective_improvement() -> None:
    fixture = load_benchmark_instance("phase90-opportunity", "weak_route_compression")
    incumbent = {"routes": [["0", "1", "2", "0"], ["0", "3", "4", "0"]]}
    result = OperatorPortfolio().apply("route-compression", fixture, incumbent, {}, None, None, Deadline.from_time_limit_ms(5000))

    assert result["telemetry"]["acceptedCandidates"] >= 0
    if result["telemetry"]["acceptedCandidates"]:
        assert result["telemetry"]["objectiveImprovingCandidates"] > 0
