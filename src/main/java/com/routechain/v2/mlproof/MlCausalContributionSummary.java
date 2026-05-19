package com.routechain.v2.mlproof;

public record MlCausalContributionSummary(boolean proven, int causalContributionCases, double contributionKm, String reason) {
}
