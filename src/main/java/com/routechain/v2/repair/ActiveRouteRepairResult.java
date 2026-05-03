package com.routechain.v2.repair;

import java.util.List;

public record ActiveRouteRepairResult(
        List<RepairCandidate> candidates,
        RepairTelemetry telemetry,
        List<String> degradeReasons) {

    public ActiveRouteRepairResult {
        candidates = candidates == null ? List.of() : List.copyOf(candidates);
        telemetry = telemetry == null ? RepairTelemetry.empty() : telemetry;
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
    }

    public static ActiveRouteRepairResult empty() {
        return new ActiveRouteRepairResult(List.of(), RepairTelemetry.empty(), List.of("active-repair-no-input"));
    }
}
