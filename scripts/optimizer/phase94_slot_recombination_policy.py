from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class SlotPolicy:
    affectedRouteCount: int
    affectedRequestCount: int
    availableRouteSlots: int
    compressionRouteSlots: int
    maxAllowedSubproblemRoutes: int
    mode: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SlotPreservingRecombinationPolicy:
    def build(self, affected_route_count: int, affected_request_count: int, mode: str = "same-slot-polish") -> SlotPolicy:
        affected_route_count = max(1, int(affected_route_count))
        compression_slots = max(1, affected_route_count - 1)
        if mode == "slot-compression" and affected_route_count > 1:
            max_allowed = compression_slots
        else:
            mode = "same-slot-polish"
            max_allowed = affected_route_count
        return SlotPolicy(
            affectedRouteCount=affected_route_count,
            affectedRequestCount=max(0, int(affected_request_count)),
            availableRouteSlots=affected_route_count,
            compressionRouteSlots=compression_slots,
            maxAllowedSubproblemRoutes=max_allowed,
            mode=mode,
        )
