package com.routechain.v2.hybrid;

import java.util.List;

public record MoveEvaluationTrace(
        String moveId,
        String routeId,
        String moveType,
        double oldKm,
        double newKm,
        double improvementKm,
        boolean accepted,
        String rejectReason,
        List<LatenessTrace> latenessTrace) {

    public MoveEvaluationTrace {
        latenessTrace = latenessTrace == null ? List.of() : List.copyOf(latenessTrace);
    }
}
