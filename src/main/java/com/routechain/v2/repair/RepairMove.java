package com.routechain.v2.repair;

public record RepairMove(
        String operatorName,
        double scoreDelta,
        String reason) {
}
