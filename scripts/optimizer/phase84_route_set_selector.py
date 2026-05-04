from __future__ import annotations

from typing import Any, Dict, List, Set

from external_benchmark_support import check_solution
from optimizer.phase84_route_pool_memory import RoutePoolMemory
from optimizer.phase84_unified_objective import UnifiedNaturalObjective


class AdaptiveRouteSetSelector:
    def select(self, instance: Dict[str, Any], incumbent: Dict[str, Any], pool: RoutePoolMemory, max_columns: int = 200) -> Dict[str, Any]:
        objective = UnifiedNaturalObjective()
        request_ids = [str(request.get("orderId", f"{request.get('pickupNodeId')}->{request.get('dropoffNodeId')}")) for request in instance.get("requests", [])]
        required: Set[str] = set(request_ids)
        columns = sorted(pool.columns.values(), key=lambda column: (len(column.requestSet), column.distance, column.signature))[:max_columns]
        selected = []
        covered: Set[str] = set()
        for column in sorted(columns, key=lambda item: (-len(set(item.requestSet) - covered), item.distance, item.signature)):
            request_set = set(column.requestSet)
            if request_set and not (request_set & covered):
                selected.append(column.route)
                covered.update(request_set)
            if covered == required:
                break
        candidate = {"schemaVersion": "external-benchmark-solution/v1", "solver": "phase84-route-set-selector", "routes": selected}
        if covered != required or not check_solution(instance, candidate).get("feasible"):
            return incumbent
        return candidate if objective.improves(instance, incumbent, candidate) else incumbent
