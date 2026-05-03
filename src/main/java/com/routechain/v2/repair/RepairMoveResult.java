package com.routechain.v2.repair;

public record RepairMoveResult(
        RepairSolution solution,
        RepairMove move,
        boolean accepted) {
}
