package com.routechain.v2.repair;

public record RepairImprovementSummary(
        double beforeBestScore,
        double afterBestScore,
        double delta,
        String bestCandidateId,
        int frozenPrefixViolationCount,
        int foodDurationViolationCount,
        double freshnessImprovementDelta,
        double tailRiskImprovementDelta) {

    public RepairImprovementSummary(
            double beforeBestScore,
            double afterBestScore,
            double delta,
            String bestCandidateId) {
        this(beforeBestScore, afterBestScore, delta, bestCandidateId, 0, 0, 0.0, 0.0);
    }

    public static RepairImprovementSummary empty() {
        return new RepairImprovementSummary(0.0, 0.0, 0.0, "", 0, 0, 0.0, 0.0);
    }
}
