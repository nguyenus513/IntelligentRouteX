package com.routechain.v2.mlproof;

public record MlPolicyContribution(String policyName, boolean used, int decisionCount, int affectedDecisionCount) {
}
