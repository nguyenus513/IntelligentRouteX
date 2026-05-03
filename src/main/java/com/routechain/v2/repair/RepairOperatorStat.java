package com.routechain.v2.repair;

public record RepairOperatorStat(
        String operatorName,
        int triedCount,
        int acceptedCount,
        int rejectedCount,
        double bestDelta,
        double avgDelta) {
}
