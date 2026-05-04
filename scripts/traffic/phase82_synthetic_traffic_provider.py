from __future__ import annotations

import time
from typing import Any, Dict, List

from traffic.phase82_traffic_provider import TrafficMatrixResult


class SyntheticTrafficProvider:
    def build_duration_matrix(self, nodes: List[Dict[str, Any]], region: str, timestamp: str, traffic_context: Dict[str, Any]) -> TrafficMatrixResult:
        started = time.perf_counter()
        base_matrix = traffic_context.get("baseDurationMatrix") or traffic_context.get("durationMatrix")
        if not base_matrix:
            size = len(nodes)
            base_matrix = [[0.0 if left == right else abs(left - right) + 5.0 for right in range(size)] for left in range(size)]
        multiplier = float(traffic_context.get("multiplier", 1.0) or 1.0)
        if traffic_context.get("rain") or traffic_context.get("trafficMode") == "rain":
            multiplier *= 1.2
        if traffic_context.get("trafficMode") == "incident":
            multiplier *= 1.5
        duration_matrix = [[0.0 if row_index == column_index else round(float(value) * multiplier, 3) for column_index, value in enumerate(row)] for row_index, row in enumerate(base_matrix)]
        context = {
            **traffic_context,
            "provider": "synthetic",
            "matrixSource": traffic_context.get("matrixSource", "synthetic"),
            "region": region,
            "generatedAt": traffic_context.get("generatedAt", timestamp),
            "freshnessSeconds": traffic_context.get("freshnessSeconds", 0),
            "confidence": traffic_context.get("confidence", 0.9),
            "multiplier": multiplier,
        }
        diagnostics = {
            "provider": "synthetic",
            "runtimeMs": int((time.perf_counter() - started) * 1000),
            "fallbackUsed": context.get("matrixSource") == "fallback",
            "fallbackReason": context.get("fallbackReason"),
            "confidence": context.get("confidence"),
            "freshnessSeconds": context.get("freshnessSeconds"),
        }
        return TrafficMatrixResult(durationMatrix=duration_matrix, distanceMatrix=duration_matrix, trafficContext=context, providerDiagnostics=diagnostics)
