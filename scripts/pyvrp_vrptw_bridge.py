from __future__ import annotations

import importlib.metadata
import importlib.util
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from external_benchmark_support import check_solution

SCALE = 1000


def finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


@dataclass(frozen=True)
class PyvrpModelConfig:
    name: str = "phase13-default"
    scale: int = SCALE
    fixed_cost: int = 1_000_000_000
    unit_distance_cost: int = 1
    unit_duration_cost: int = 0
    duration_includes_service: bool = True
    demand_mode: str = "delivery"


def pyvrp_available() -> bool:
    return importlib.util.find_spec("pyvrp") is not None


def pyvrp_version() -> str:
    try:
        return importlib.metadata.version("pyvrp")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def build_model(instance: dict[str, Any], config: PyvrpModelConfig | None = None) -> tuple[Any, list[str]]:
    from pyvrp import Model  # type: ignore

    config = config or PyvrpModelConfig()
    if instance.get("problemType") != "VRPTW":
        raise ValueError(f"PyVRP bridge supports VRPTW only, got {instance.get('problemType')}")
    nodes = instance.get("nodes", [])
    if not nodes:
        raise ValueError("instance has no nodes")
    depot_id = str(instance.get("depotNodeId", "0"))
    depot_index = next((idx for idx, node in enumerate(nodes) if str(node.get("id")) == depot_id), 0)
    ordered_nodes = [nodes[depot_index]] + [node for idx, node in enumerate(nodes) if idx != depot_index]
    node_ids = [str(node["id"]) for node in ordered_nodes]
    original_index = {str(node["id"]): idx for idx, node in enumerate(nodes)}

    model = Model()
    depot_node = ordered_nodes[0]
    depot = model.add_depot(
        x=float(depot_node.get("x", 0.0)),
        y=float(depot_node.get("y", 0.0)),
        tw_early=int(round(float(depot_node.get("readyTime", 0.0)) * config.scale)),
        tw_late=int(round(float(depot_node.get("dueTime", 0.0)) * config.scale)),
        service_duration=int(round(float(depot_node.get("serviceTime", 0.0)) * config.scale)),
        name=str(depot_node["id"]),
    )
    locations = [depot]
    for node in ordered_nodes[1:]:
        demand = max(0, int(round(float(node.get("demand", 0.0)))))
        client_args = {
            "x": float(node.get("x", 0.0)),
            "y": float(node.get("y", 0.0)),
            "service_duration": int(round(float(node.get("serviceTime", 0.0)) * config.scale)),
            "tw_early": int(round(float(node.get("readyTime", 0.0)) * config.scale)),
            "tw_late": int(round(float(node.get("dueTime", 0.0)) * config.scale)),
            "name": str(node["id"]),
        }
        if config.demand_mode == "pickup":
            client_args["pickup"] = demand
        else:
            client_args["delivery"] = demand
        locations.append(model.add_client(**client_args))
    model.add_vehicle_type(
        num_available=int(instance.get("vehicleCount", len(nodes))),
        capacity=int(round(float(instance.get("capacity", 0)))) if instance.get("capacity", 0) else [],
        start_depot=depot,
        end_depot=depot,
        fixed_cost=config.fixed_cost,
        unit_distance_cost=config.unit_distance_cost,
        unit_duration_cost=config.unit_duration_cost,
        name=f"{config.name}-vehicle",
    )
    matrix = instance.get("distanceMatrix", [])
    for left_pos, left_node in enumerate(ordered_nodes):
        left_original = original_index[str(left_node["id"])]
        for right_pos, right_node in enumerate(ordered_nodes):
            right_original = original_index[str(right_node["id"])]
            if left_pos == right_pos:
                model.add_edge(locations[left_pos], locations[right_pos], distance=0, duration=0)
                continue
            distance = int(round(float(matrix[left_original][right_original]) * config.scale))
            service = int(round(float(left_node.get("serviceTime", 0.0)) * config.scale)) if config.duration_includes_service else 0
            model.add_edge(locations[left_pos], locations[right_pos], distance=distance, duration=distance + service)
    return model, node_ids


def solution_from_result(result: Any, node_ids: list[str], solver: str) -> dict[str, Any]:
    routes = []
    for route in result.best.routes():
        visits = [int(visit) for visit in route.visits()]
        if not visits:
            continue
        routes.append([node_ids[0]] + [node_ids[index] for index in visits] + [node_ids[0]])
    return {
        "schemaVersion": "external-benchmark-solution/v1",
        "solver": solver,
        "routes": routes,
        "pyvrpCost": finite_or_none(result.cost() if callable(getattr(result, "cost", None)) else None),
        "pyvrpRuntimeSeconds": finite_or_none(result.runtime if hasattr(result, "runtime") else None),
        "pyvrpFeasible": bool(result.is_feasible()) if callable(getattr(result, "is_feasible", None)) else None,
        "pyvrpIterations": int(result.num_iterations) if hasattr(result, "num_iterations") else None,
    }


def solve_vrptw(instance: dict[str, Any], time_limit_ms: int, seed: int = 13, config: PyvrpModelConfig | None = None) -> dict[str, Any]:
    config = config or PyvrpModelConfig()
    if not pyvrp_available():
        return {
            "schemaVersion": "external-benchmark-solution/v1",
            "solver": f"pyvrp-hgs-vrptw:{config.name}",
            "routes": [],
            "status": "SKIPPED",
            "evidenceGapReason": "pyvrp-package-not-installed",
            "pyvrpAvailable": False,
        }
    started = time.perf_counter()
    try:
        from pyvrp.stop import MaxRuntime  # type: ignore
        model, node_ids = build_model(instance, config)
        result = model.solve(stop=MaxRuntime(max(0.1, time_limit_ms / 1000.0)), seed=seed, display=False)
        solution = solution_from_result(result, node_ids, f"pyvrp-hgs-vrptw:{config.name}")
        checked = check_solution(instance, solution)
        solution.update({
            "status": "PASS" if checked.get("feasible") else "FAIL",
            "pyvrpAvailable": True,
            "pyvrpVersion": pyvrp_version(),
            "pyvrpModelConfig": config.__dict__,
            "runtimeMs": int((time.perf_counter() - started) * 1000),
            "checked": checked,
        })
        return solution
    except Exception as exception:
        return {
            "schemaVersion": "external-benchmark-solution/v1",
            "solver": f"pyvrp-hgs-vrptw:{config.name}",
            "routes": [],
            "status": "ERROR",
            "evidenceGapReason": f"pyvrp-bridge-error: {type(exception).__name__}: {exception}",
            "pyvrpAvailable": True,
            "pyvrpVersion": pyvrp_version(),
            "pyvrpModelConfig": config.__dict__,
            "runtimeMs": int((time.perf_counter() - started) * 1000),
        }


