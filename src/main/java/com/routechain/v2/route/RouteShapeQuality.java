package com.routechain.v2.route;

import java.util.ArrayList;
import java.util.List;

public final class RouteShapeQuality {
    public static final double STRAIGHTNESS_FLOOR = 0.55;
    public static final double STRAIGHTNESS_REJECT_FLOOR = 0.35;
    public static final int TURN_COUNT_SOFT_LIMIT = 20;
    public static final int TURN_COUNT_REJECT_LIMIT = 36;
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

    public static String verdict(RouteProposal proposal) {
        if (proposal == null || !proposal.geometryAvailable()) {
            return "UNKNOWN";
        }
        if (proposal.stopOrder().size() > 1
                && (proposal.straightnessScore() < STRAIGHTNESS_REJECT_FLOOR
                || proposal.turnCount() > TURN_COUNT_REJECT_LIMIT)) {
            return "REJECT_SHAPE";
        }
        if (proposal.straightnessScore() < STRAIGHTNESS_FLOOR
                || proposal.turnCount() > TURN_COUNT_SOFT_LIMIT
                || (proposal.congestionScore() >= CONGESTION_HIGH_RISK && proposal.straightnessScore() < 0.65)) {
            return "ZIGZAG_RISK";
        }
        if (proposal.straightnessScore() < 0.70 || proposal.turnCount() > 14) {
            return "ACCEPTABLE";
        }
        return "GOOD";
    }

    public static boolean dominates(RouteProposal candidate, RouteProposal dominated) {
        if (candidate == null || dominated == null || !candidate.geometryAvailable() || !dominated.geometryAvailable()) {
            return false;
        }
        if (!sameOrderSet(candidate, dominated)) {
            return false;
        }
        boolean noWorse = candidate.routeCost() <= dominated.routeCost() + 1e-9
                && candidate.totalTravelTimeSeconds() <= dominated.totalTravelTimeSeconds() + 1e-9
                && candidate.turnCount() <= dominated.turnCount()
                && candidate.straightnessScore() + 1e-9 >= dominated.straightnessScore()
                && candidate.congestionScore() <= dominated.congestionScore() + 1e-9;
        boolean materiallyBetter = candidate.routeCost() < dominated.routeCost() - 25.0
                || candidate.totalTravelTimeSeconds() < dominated.totalTravelTimeSeconds() - 10.0
                || candidate.turnCount() < dominated.turnCount()
                || candidate.straightnessScore() > dominated.straightnessScore() + 0.03
                || penalty(candidate) + 0.03 < penalty(dominated);
        return noWorse && materiallyBetter;
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

    private static boolean sameOrderSet(RouteProposal left, RouteProposal right) {
        return new java.util.HashSet<>(left.stopOrder()).equals(new java.util.HashSet<>(right.stopOrder()));
    }
}
