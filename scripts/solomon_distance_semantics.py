from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


DISTANCE_MODES = (
    "euclidean_float",
    "euclidean_round_nearest",
    "euclidean_floor",
    "euclidean_ceil",
    "euclidean_one_decimal",
    "euclidean_truncate_1_decimal",
    "scaled_1000_current",
)


def euclidean(left: dict[str, Any], right: dict[str, Any]) -> float:
    return math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"]))


def transform_distance(value: float, mode: str) -> float:
    if mode == "euclidean_float":
        return value
    if mode == "euclidean_round_nearest":
        return float(round(value))
    if mode == "euclidean_floor":
        return float(math.floor(value))
    if mode == "euclidean_ceil":
        return float(math.ceil(value))
    if mode == "euclidean_one_decimal":
        return round(value, 1)
    if mode == "euclidean_truncate_1_decimal":
        return math.trunc(value * 10.0) / 10.0
    if mode == "scaled_1000_current":
        return round(value * 1000.0) / 1000.0
    raise ValueError(f"Unsupported distance mode: {mode}")


def distance_matrix(nodes: list[dict[str, Any]], mode: str) -> list[list[float]]:
    return [[transform_distance(euclidean(left, right), mode) for right in nodes] for left in nodes]


def instance_with_distance_mode(instance: dict[str, Any], mode: str) -> dict[str, Any]:
    copy = deepcopy(instance)
    matrix = distance_matrix(copy.get("nodes", []), mode)
    copy["distanceMatrix"] = matrix
    copy["durationMatrix"] = matrix
    copy["distanceMode"] = mode
    return copy


def route_total_distance(instance: dict[str, Any], route: list[str]) -> float:
    index = {str(node["id"]): position for position, node in enumerate(instance.get("nodes", []))}
    total = 0.0
    for left, right in zip(route, route[1:]):
        total += float(instance["distanceMatrix"][index[str(left)]][index[str(right)]])
    return total
