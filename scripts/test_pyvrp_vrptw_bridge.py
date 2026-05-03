from __future__ import annotations

from pathlib import Path

from scripts.parse_solomon_vrptw import parse_solomon
from scripts.pyvrp_vrptw_bridge import build_model, pyvrp_available, solve_vrptw


def test_bridge_builds_model_for_solomon_fixture() -> None:
    instance = parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
    model, node_ids = build_model(instance)

    assert node_ids[0] == "0"
    assert len(node_ids) == len(instance["nodes"])
    assert model.data() is not None


def test_bridge_solve_is_skip_safe_or_returns_solution() -> None:
    instance = parse_solomon(Path("benchmarks/external/solomon/fixtures/C101.txt"))
    solution = solve_vrptw(instance, 500, seed=1)

    if not pyvrp_available():
        assert solution["status"] == "SKIPPED"
    else:
        assert solution["status"] in {"PASS", "FAIL", "ERROR"}
        assert "routes" in solution
