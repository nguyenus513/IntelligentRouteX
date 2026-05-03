package com.routechain.v2.repair;

import java.util.List;

public final class ActiveRouteRepairService {
    private final AlnsRepairEngine repairEngine = new AlnsRepairEngine();

    public List<RepairCandidate> evaluate(RepairContext context) {
        return evaluateWithTelemetry(context).candidates();
    }

    public ActiveRouteRepairResult evaluateWithTelemetry(RepairContext context) {
        if (context == null || context.insertionCandidates() == null || context.insertionCandidates().isEmpty()) {
            return ActiveRouteRepairResult.empty();
        }
        return repairEngine.repairWithTelemetry(context);
    }
}
