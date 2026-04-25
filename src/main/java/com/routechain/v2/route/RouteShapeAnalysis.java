package com.routechain.v2.route;

import java.util.List;

public record RouteShapeAnalysis(
        String schemaVersion,
        String verdict,
        double penalty,
        double detourRatio,
        double turnDensity,
        int backtrackCount,
        int crossingCount,
        int zigzagChangeCount,
        double shapeScore,
        List<String> reasons) {
}
