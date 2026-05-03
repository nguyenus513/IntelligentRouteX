package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record DispatchDecisionAgreementSummary(
        String schemaVersion,
        int comparedStageCount,
        int exactMatchStageCount,
        double overallExactMatchRate,
        List<DispatchDecisionStageAgreement> stageAgreements) implements SchemaVersioned {

    public DispatchDecisionAgreementSummary {
        stageAgreements = stageAgreements == null ? List.of() : List.copyOf(stageAgreements);
    }

    public static DispatchDecisionAgreementSummary empty() {
        return new DispatchDecisionAgreementSummary(
                "dispatch-decision-agreement-summary/v1",
                0,
                0,
                0.0,
                List.of());
    }
}
