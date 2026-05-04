from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def matrix_errors(matrix: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(matrix, list) or not matrix:
        return ["durationMatrix: missing-or-empty"]
    size = len(matrix)
    for row_index, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != size:
            errors.append(f"durationMatrix[{row_index}]: non-square")
            continue
        for column_index, value in enumerate(row):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"durationMatrix[{row_index}][{column_index}]: non-numeric")
            elif value < 0:
                errors.append(f"durationMatrix[{row_index}][{column_index}]: negative-duration")
        if row_index < len(row) and isinstance(row[row_index], (int, float)) and row[row_index] != 0:
            errors.append(f"durationMatrix[{row_index}][{row_index}]: diagonal-not-zero")
    return errors


def active_route_traffic_risk(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    matrix = snapshot.get("durationMatrix", [])
    node_ids = [str(node_id) for node_id in snapshot.get("nodeIds", [])]
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    risks = []
    for active_route in snapshot.get("activeRoutes", []):
        route = [str(node_id) for node_id in active_route.get("route", [])]
        locked_length = int(active_route.get("lockedPrefixLength", 0) or 0)
        prefix = route[:locked_length]
        elapsed = 0.0
        for left, right in zip(prefix, prefix[1:]):
            if left not in index or right not in index:
                risks.append({"driverId": active_route.get("driverId"), "reason": "unknown-locked-node"})
                break
            elapsed += float(matrix[index[left]][index[right]])
        threshold = float(snapshot.get("trafficContext", {}).get("activeRouteRiskThreshold", 60) or 60)
        if elapsed > threshold:
            risks.append({"driverId": active_route.get("driverId"), "reason": "locked-prefix-duration-risk", "lockedPrefixDuration": elapsed, "threshold": threshold})
    return {"activeRouteTrafficRiskCount": len(risks), "risks": risks}


def audit_traffic_matrix(snapshot: Dict[str, Any], max_freshness_seconds: int = 300, min_confidence: float = 0.7, require_live_traffic: bool = False, allow_traffic_fallback: bool = False) -> Dict[str, Any]:
    errors = matrix_errors(snapshot.get("durationMatrix"))
    traffic = snapshot.get("trafficContext", {}) if isinstance(snapshot.get("trafficContext"), dict) else {}
    confidence = traffic.get("confidence")
    freshness = traffic.get("freshnessSeconds")
    matrix_source = str(traffic.get("matrixSource", "unknown"))
    provider = str(traffic.get("provider", "unknown"))
    generated_at = parse_timestamp(traffic.get("generatedAt"))
    valid_until = parse_timestamp(traffic.get("validUntil"))
    snapshot_time = parse_timestamp(snapshot.get("timestamp"))
    warnings: List[str] = []

    if generated_at is None and traffic.get("generatedAt") is not None:
        errors.append("trafficContext.generatedAt: invalid-timestamp")
    if valid_until is None and traffic.get("validUntil") is not None:
        errors.append("trafficContext.validUntil: invalid-timestamp")
    if generated_at and snapshot_time and generated_at > snapshot_time:
        errors.append("trafficContext.generatedAt: after-snapshot-timestamp")
    if valid_until and snapshot_time and valid_until < snapshot_time:
        warnings.append("trafficContext.validUntil: expired")
    if confidence is not None and (not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or confidence < 0 or confidence > 1):
        errors.append("trafficContext.confidence: outside-[0,1]")
    if freshness is not None and (not isinstance(freshness, (int, float)) or isinstance(freshness, bool) or freshness < 0):
        errors.append("trafficContext.freshnessSeconds: invalid")

    stale = freshness is not None and isinstance(freshness, (int, float)) and freshness > max_freshness_seconds
    low_confidence = confidence is not None and isinstance(confidence, (int, float)) and confidence < min_confidence
    fallback_used = matrix_source == "fallback"
    active_route_risk = active_route_traffic_risk(snapshot) if not errors else {"activeRouteTrafficRiskCount": 0, "risks": []}
    if require_live_traffic and matrix_source != "live":
        warnings.append("trafficContext.matrixSource: live-required")

    if errors:
        classification = "traffic-matrix-invalid"
    elif active_route_risk.get("activeRouteTrafficRiskCount", 0) > 0:
        classification = "active-route-traffic-risk"
    elif stale and not allow_traffic_fallback:
        classification = "traffic-matrix-stale"
    elif low_confidence and not allow_traffic_fallback:
        classification = "traffic-confidence-low"
    elif fallback_used or (allow_traffic_fallback and (stale or low_confidence or matrix_source != "live" and require_live_traffic)):
        classification = "traffic-fallback-used"
    else:
        classification = "traffic-matrix-healthy"

    fallback_required = classification in {"traffic-matrix-invalid", "traffic-matrix-stale", "traffic-confidence-low", "active-route-traffic-risk"}
    return {
        "snapshotId": snapshot.get("snapshotId"),
        "classification": classification,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "fallbackRequired": fallback_required,
        "fallbackUsed": fallback_used or classification == "traffic-fallback-used",
        "activeRouteTrafficRiskCount": active_route_risk.get("activeRouteTrafficRiskCount", 0),
        "activeRouteTrafficRisks": active_route_risk.get("risks", []),
        "provider": provider,
        "matrixSource": matrix_source,
        "confidence": confidence,
        "freshnessSeconds": freshness,
        "maxFreshnessSeconds": max_freshness_seconds,
        "minConfidence": min_confidence,
    }
