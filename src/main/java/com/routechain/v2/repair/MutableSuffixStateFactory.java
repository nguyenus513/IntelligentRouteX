package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import java.util.List;

public final class MutableSuffixStateFactory {
    public MutableSuffixState fromCandidate(ActiveRouteInsertionCandidate candidate) {
        return new MutableSuffixState(
                candidate.routeId(),
                candidate.driverId(),
                List.of(),
                candidate.newStopOrder(),
                List.of(),
                candidate.insertedOrderId(),
                candidate.score(),
                candidate.feasible(),
                candidate.degradeReasons(),
                candidate.reasons());
    }
}
