import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List


def _load_runtime_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _lite_runtime_enabled() -> bool:
    return os.getenv("IRX_GREEDRL_RUNTIME_MODE", "").strip().lower() == "lite"


def _requested_device() -> str:
    return os.getenv("IRX_GREEDRL_WORKER_DEVICE", os.getenv("IRX_ML_WORKER_DEVICE", "cpu")).strip() or "cpu"


def _strict_device_enabled() -> bool:
    return os.getenv("IRX_GREEDRL_STRICT_DEVICE", os.getenv("IRX_ML_STRICT_DEVICE", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _device_audit() -> Dict[str, Any]:
    requested = _requested_device()
    normalized = requested.lower()
    if normalized in {"auto", "gpu", "cuda"}:
        requested = "cuda:0"
        normalized = requested
    if not normalized.startswith("cuda"):
        return {
            "device": "cpu",
            "requestedDevice": requested,
            "gpuAcceleration": False,
            "gpuAccelerationReason": "cpu-selected",
        }
    try:
        import torch

        cuda_available = bool(hasattr(torch, "cuda") and torch.cuda.is_available())
    except Exception as exc:
        if _strict_device_enabled():
            raise RuntimeError(f"greedrl-cuda-probe-failed:{type(exc).__name__}:{exc}") from exc
        return {
            "device": "cpu",
            "requestedDevice": requested,
            "gpuAcceleration": False,
            "gpuAccelerationReason": "cuda-requested-but-torch-probe-failed-fallback-cpu",
        }
    if cuda_available:
        return {
            "device": requested,
            "requestedDevice": requested,
            "gpuAcceleration": True,
            "gpuAccelerationReason": "cuda-available",
        }
    if _strict_device_enabled():
        raise RuntimeError("greedrl-cuda-requested-but-unavailable")
    return {
        "device": "cpu",
        "requestedDevice": requested,
        "gpuAcceleration": False,
        "gpuAccelerationReason": "cuda-requested-but-unavailable-fallback-cpu",
    }


def _import_runtime_modules() -> None:
    if _lite_runtime_enabled():
        return
    __import__("greedrl")
    __import__("greedrl_c")


def _score_bundle(order_ids: List[str], payload: Dict[str, Any], runtime_manifest: Dict[str, Any]) -> float:
    bundle_config = runtime_manifest.get("bundleProposal", {})
    support = payload.get("supportScoreByOrder", {})
    support_score = sum(float(support.get(order_id, 0.0)) for order_id in order_ids)
    boundary_bonus = float(bundle_config.get("boundaryBonus", 0.0)) if any(
        order_id in payload.get("acceptedBoundaryOrderIds", []) for order_id in order_ids
    ) else 0.0
    size_bonus = len(order_ids) * float(bundle_config.get("perOrderBonus", 0.0))
    signature = "|".join(order_ids).encode("utf-8")
    tie_break = (int(hashlib.sha256(signature).hexdigest()[:6], 16) / 0xFFFFFF) * float(
        bundle_config.get("lexicalTieBreakScale", 0.0)
    )
    return support_score + boundary_bonus + size_bonus + tie_break


def _family_for(order_ids: List[str], payload: Dict[str, Any]) -> str:
    accepted_boundary = set(payload.get("acceptedBoundaryOrderIds", []))
    if accepted_boundary.intersection(order_ids):
        return "BOUNDARY_CROSS"
    if len(order_ids) >= 3:
        return "CORRIDOR_CHAIN"
    return "COMPACT_CLIQUE"


def _candidate_order_sets(payload: Dict[str, Any], runtime_manifest: Dict[str, Any]) -> List[List[str]]:
    bundle_config = runtime_manifest.get("bundleProposal", {})
    max_size = max(1, min(int(payload.get("bundleMaxSize", 1)), int(bundle_config.get("maxBundleSize", 3))))
    max_proposals = max(1, min(int(payload.get("maxProposals", 1)), int(bundle_config.get("maxGeneratedProposals", 3))))
    prioritized = list(dict.fromkeys(payload.get("prioritizedOrderIds", [])))
    accepted_boundary = [order_id for order_id in payload.get("acceptedBoundaryOrderIds", []) if order_id not in prioritized]
    working = [order_id for order_id in payload.get("workingOrderIds", []) if order_id not in prioritized]
    ordered_pool = prioritized + accepted_boundary + working
    candidates: List[List[str]] = []
    if prioritized:
        for start in range(min(len(prioritized), max_proposals)):
            seed = prioritized[start]
            candidate = [seed]
            for order_id in ordered_pool:
                if order_id not in candidate:
                    candidate.append(order_id)
                if len(candidate) >= max_size:
                    break
            candidates.append(sorted(set(candidate)))
    if not candidates and ordered_pool:
        candidates.append(sorted(set(ordered_pool[:max_size])))
    unique: List[List[str]] = []
    seen = set()
    for candidate in candidates:
        signature = "|".join(candidate)
        if signature not in seen:
            seen.add(signature)
            unique.append(candidate)
    return unique[:max_proposals]


def _bundle_proposals(payload: Dict[str, Any], runtime_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    ranked = []
    for order_ids in _candidate_order_sets(payload, runtime_manifest):
        ranked.append(
            {
                "family": _family_for(order_ids, payload),
                "orderIds": order_ids,
                "acceptedBoundaryOrderIds": [
                    order_id for order_id in order_ids if order_id in payload.get("acceptedBoundaryOrderIds", [])
                ],
                "boundaryCross": any(order_id in payload.get("acceptedBoundaryOrderIds", []) for order_id in order_ids),
                "traceReasons": [
                    "greedrl-bundle-proposal",
                    "greedrl-lite-runtime" if _lite_runtime_enabled() else "greedrl-native-runtime",
                    "signature:{0}".format("|".join(order_ids)),
                ],
                "_score": _score_bundle(order_ids, payload, runtime_manifest),
            }
        )
    ranked.sort(key=lambda candidate: (-candidate["_score"], -len(candidate["orderIds"]), "|".join(candidate["orderIds"])))
    return [{key: value for key, value in candidate.items() if key != "_score"} for candidate in ranked]


def _sequence_proposals(payload: Dict[str, Any], runtime_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    sequence_config = runtime_manifest.get("sequenceProposal", {})
    order_ids = list(dict.fromkeys(payload.get("orderIds") or payload.get("workingOrderIds", [])))
    if not order_ids:
        return []
    anchor_order_id = payload.get("anchorOrderId") or order_ids[0]
    remainder = [order_id for order_id in order_ids if order_id != anchor_order_id]
    sequences = [[anchor_order_id] + remainder, [anchor_order_id] + list(reversed(remainder))]
    unique: List[List[str]] = []
    seen = set()
    for sequence in sequences:
        signature = ">".join(sequence)
        if signature not in seen:
            seen.add(signature)
            unique.append(sequence)
    max_sequences = max(1, min(int(payload.get("maxSequences", 2)), int(sequence_config.get("maxGeneratedSequences", 2))))
    return [
        {
            "stopOrder": sequence,
            "sequenceScore": float(sequence_config.get("baseScore", 0.7)) - index * float(sequence_config.get("decayPerAlternative", 0.05)),
            "traceReasons": [
                "greedrl-sequence-proposal",
                "greedrl-lite-runtime" if _lite_runtime_enabled() else "greedrl-native-runtime",
                "signature:{0}".format(">".join(sequence)),
            ],
        }
        for index, sequence in enumerate(unique[:max_sequences])
    ]


def _self_check() -> Dict[str, Any]:
    _import_runtime_modules()
    return {"ok": True, "runtimeMode": "lite" if _lite_runtime_enabled() else "native", **_device_audit()}


def _dispatch(action: str, payload: Dict[str, Any], runtime_manifest: Dict[str, Any]) -> Dict[str, Any]:
    _import_runtime_modules()
    if action == "self-check":
        return _self_check()
    if action == "bundle-propose":
        return {"bundleProposals": _bundle_proposals(payload, runtime_manifest), "sequenceProposals": []}
    if action == "sequence-propose":
        return {"bundleProposals": [], "sequenceProposals": _sequence_proposals(payload, runtime_manifest)}
    raise ValueError("unsupported-action:{0}".format(action))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-manifest", required=True)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    runtime_manifest = _load_runtime_manifest(Path(args.runtime_manifest))
    if args.serve:
        for line in sys.stdin:
            try:
                request = json.loads(line or "{}")
                response = _dispatch(request.get("action", ""), request.get("payload") or {}, runtime_manifest)
            except Exception as exc:
                response = {"error": f"{type(exc).__name__}:{exc}"}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        return 0
    request = json.loads(sys.stdin.read() or "{}")
    sys.stdout.write(json.dumps(_dispatch(request.get("action", ""), request.get("payload") or {}, runtime_manifest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
