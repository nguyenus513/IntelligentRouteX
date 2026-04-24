package com.routechain.v2.route;

import java.util.ArrayList;
import java.util.List;

public final class RouteShapeQuality {
    public static final double STRAIGHTNESS_FLOOR = 0.55;
    public static final int TURN_COUNT_SOFT_LIMIT = 20;
    public static final double CONGESTION_HIGH_RISK = 0.90;

    private RouteShapeQuality() {
    }

    public static double penalty(RouteProposal proposal) {
        if (proposal == null || !proposal.geometryAvailable()) {
            return 0.0;
        }
        double straightnessPenalty = Math.max(0.0, STRAIGHTNESS_FLOOR - proposal.straightnessScore()) * 0.60;
        double turnPenalty = Math.min(0.15, Math.max(0, proposal.turnCount() - TURN_COUNT_SOFT_LIMIT) * 0.006);
        double congestionPenalty = proposal.congestionScore() >= CONGESTION_HIGH_RISK
                && proposal.straightnessScore() < STRAIGHTNESS_FLOOR ? 0.04 : 0.0;
        return Math.min(0.32, straightnessPenalty + turnPenalty + congestionPenalty);
    }

    public static List<String> reasons(RouteProposal proposal) {
        if (proposal == null || !proposal.geometryAvailable()) {
            return List.of();
        }
        List<String> reasons = new ArrayList<>();
        if (proposal.straightnessScore() < STRAIGHTNESS_FLOOR) {
            reasons.add("route-shape-straightness-penalty");
        }
        if (proposal.turnCount() > TURN_COUNT_SOFT_LIMIT) {
            reasons.add("route-shape-turn-penalty");
        }
        if (proposal.congestionScore() >= CONGESTION_HIGH_RISK && proposal.straightnessScore() < STRAIGHTNESS_FLOOR) {
            reasons.add("route-shape-congestion-zigzag-penalty");
        }
        return List.copyOf(reasons);
    }
}
