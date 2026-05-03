package com.routechain.v2.benchmark;

record DispatchQualityFeedbackSummary(
        DispatchDecisionAgreementSummary decisionAgreement,
        DispatchTokenUsageSummary tokenUsageSummary,
        DispatchStageFallbackSummary stageFallbackSummary) {

    static DispatchQualityFeedbackSummary empty() {
        return new DispatchQualityFeedbackSummary(
                DispatchDecisionAgreementSummary.empty(),
                DispatchTokenUsageSummary.empty(),
                DispatchStageFallbackSummary.empty());
    }
}
