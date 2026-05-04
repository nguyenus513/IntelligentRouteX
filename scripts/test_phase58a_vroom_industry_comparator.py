from __future__ import annotations

import inspect

import run_phase58a_vroom_industry_comparator as phase58a


def tiny_instance() -> dict:
    return {
        "instanceName": "tiny",
        "depotNodeId": "0",
        "vehicleCount": 2,
        "capacity": 10,
        "nodes": [
            {"id": "0", "readyTime": 0, "dueTime": 100, "serviceTime": 0, "demand": 0},
            {"id": "1", "readyTime": 0, "dueTime": 100, "serviceTime": 2, "demand": 1},
            {"id": "2", "readyTime": 0, "dueTime": 100, "serviceTime": 3, "demand": -1},
        ],
        "distanceMatrix": [[0, 1, 2], [1, 0, 1], [2, 1, 0]],
        "requests": [{"pickupNodeId": "1", "dropoffNodeId": "2"}],
    }


def test_converts_pdptw_requests_to_vroom_shipments() -> None:
    request = phase58a.convert_pdptw_to_vroom(tiny_instance())

    assert len(request["shipments"]) == 1
    assert request["shipments"][0]["pickup"]["description"] == "1"
    assert request["shipments"][0]["delivery"]["description"] == "2"
    assert len(request["vehicles"]) == 2


def test_converts_vroom_route_to_internal_route() -> None:
    payload = {"routes": [{"steps": [{"type": "start"}, {"type": "pickup", "description": "1"}, {"type": "delivery", "description": "2"}, {"type": "end"}]}]}

    solution = phase58a.vroom_output_to_solution(tiny_instance(), payload)

    assert solution["routes"] == [["0", "1", "2", "0"]]


def test_maps_vroom_pickup_delivery_steps_by_shipment_id() -> None:
    instance = tiny_instance()
    request = phase58a.convert_pdptw_to_vroom(instance)
    payload = {"routes": [{"steps": [{"type": "start"}, {"type": "pickup", "id": 1}, {"type": "delivery", "id": 2}, {"type": "end"}]}]}

    solution = phase58a.vroom_output_to_solution(instance, payload, request)

    assert solution["routes"] == [["0", "1", "2", "0"]]
    assert {step["mappingSource"] for step in solution["vroomStepMappingTrace"] if step["mappedNodeId"]} == {"shipment-step-id"}


def test_falls_back_to_description_mapping() -> None:
    mapped = phase58a.map_vroom_step({"type": "pickup", "description": "1"}, {}, {})

    assert mapped == {"nodeId": "1", "source": "description", "ambiguous": False}


def test_detects_ambiguous_vroom_step_mapping() -> None:
    mapped = phase58a.map_vroom_step({"type": "pickup", "id": 1, "description": "2"}, {("pickup", 1): "1"}, {})

    assert mapped["ambiguous"]
    assert mapped["source"] == "ambiguous"


def test_validates_exact_coverage_and_rejects_incomplete_mapping() -> None:
    complete = {"routes": [["0", "1", "2", "0"]]}
    incomplete = {"routes": [["0", "1", "0"]]}

    assert phase58a.exact_pair_coverage(tiny_instance(), complete)["valid"]
    assert not phase58a.exact_pair_coverage(tiny_instance(), incomplete)["valid"]


def test_classifies_challenger_win_vroom_win_and_tie() -> None:
    champion = {"hardViolations": 0, "vehicleCount": 2, "totalDistance": 100.0}
    challenger = {"hardViolations": 0, "vehicleCount": 1, "totalDistance": 150.0}
    assert phase58a.classify(champion, challenger, False, False) == "challenger-win"

    challenger = {"hardViolations": 0, "vehicleCount": 3, "totalDistance": 50.0}
    assert phase58a.classify(champion, challenger, False, False) == "vroom-win"

    challenger = {"hardViolations": 0, "vehicleCount": 2, "totalDistance": 100.5}
    assert phase58a.classify(champion, challenger, False, False, distance_tolerance=0.01) == "tie"


def test_handles_vroom_unavailable() -> None:
    assert phase58a.classify({}, {"hardViolations": 0}, False, True) == "vroom-unavailable"


def test_classifies_vroom_timeout_separately() -> None:
    assert phase58a.classify({}, {"hardViolations": 0}, False, True, vroom_status="vroom-timeout") == "vroom-timeout"


def test_classifies_import_failure_separately() -> None:
    assert phase58a.classify({}, {"hardViolations": 0}, False, False, import_valid=False) == "vroom-import-fail"


def test_detects_matrix_time_window_scale_mismatch() -> None:
    instance = tiny_instance()
    request = phase58a.convert_pdptw_to_vroom(instance)
    request["matrices"]["car"]["durations"] = [[0, 10_000, 20_000], [10_000, 0, 10_000], [20_000, 10_000, 0]]

    diagnostics = phase58a.time_unit_diagnostics(instance, request)

    assert "matrix-too-large-vs-time-windows" in diagnostics["suspiciousScaleMismatch"]


def test_validates_vroom_request_and_hashes_raw_request() -> None:
    request = phase58a.convert_pdptw_to_vroom(tiny_instance())

    validation = phase58a.validate_vroom_request(request, 3)

    assert validation["valid"]
    assert len(phase58a.request_hash(request)) == 64


def test_no_instance_name_branch() -> None:
    source = inspect.getsource(phase58a)
    assert "startswith(\"LRC\")" not in source
    assert "startswith('LRC')" not in source
    assert "instanceName ==" not in source
