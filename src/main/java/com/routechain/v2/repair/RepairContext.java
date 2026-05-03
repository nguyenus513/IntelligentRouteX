package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.active.ActiveRouteState;

import java.time.Duration;
import java.util.List;

public record RepairContext(
        List<ActiveRouteState> activeRoutes,
        List<ActiveRouteInsertionCandidate> insertionCandidates,
        Duration runtimeBudget) {
}
