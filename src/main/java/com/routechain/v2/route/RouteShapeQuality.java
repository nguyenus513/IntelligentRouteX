package com.routechain.v2.route;

import com.routechain.v2.routing.LegRouteVector;

import java.util.ArrayList;
import java.util.List;

public final class RouteShapeQuality {
    public static final double STRAIGHTNESS_FLOOR = 0.55;
    public static final double STRAIGHTNESS_REJECT_FLOOR = 0.35;
    public static final double MULTI_ORDER_STRAIGHTNESS_REJECT_FLOOR = 0.50;
    public static final double MULTI_ORDER_STRAIGHTNESS_WEAK_FLOOR = 0.60;
    public static final int TURN_COUNT_SOFT_LIMIT = 20;
    public static final int MULTI_ORDER_TURN_WEAK_LIMIT = 16;
    public static final int TURN_COUNT_REJECT_LIMIT = 36;
    public static final double CONGESTION_HIGH_RISK = 0.90;
    public static final double CONGESTION_SELECTED_REJECT_RISK = 0.95;
    public static final double DETOUR_WEAK_RATIO = 1.65;
    public static final double DETOUR_REJECT_RATIO = 2.30;
    public static final double TURN_DENSITY_WEAK_LIMIT = 16.0;
    public static final double TURN_DENSITY_REJECT_LIMIT = 28.0;

    private RouteShapeQuality() {
    }

    public static double penalty(RouteProposal proposal) {
        return analyze(proposal).penalty();
    }

    public static String verdict(RouteProposal proposal) {
        return analyze(proposal).verdict();
    }

    public static RouteShapeAnalysis analyze(RouteProposal proposal) {
        if (proposal == null || !proposal.geometryAvailable()) {
            return new RouteShapeAnalysis("route-shape-analysis/v1", "UNKNOWN", 0.0, 1.0, 0.0, 0, 0, 0, 0.0, List.of());
        }
        double detourRatio = detourRatio(proposal);
        double turnDensity = turnDensity(proposal);
        int backtrackCount = backtrackCount(proposal.legs());
        int crossingCount = crossingCount(proposal.legs());
        int zigzagChangeCount = zigzagChangeCount(proposal.legs());
        List<String> reasons = reasons(proposal, detourRatio, turnDensity, backtrackCount, crossingCount, zigzagChangeCount);
        double straightnessPenalty = Math.max(0.0, STRAIGHTNESS_FLOOR - proposal.straightnessScore()) * 0.70;
        double turnPenalty = Math.min(0.18, Math.max(0, proposal.turnCount() - TURN_COUNT_SOFT_LIMIT) * 0.007);
        double detourPenalty = Math.min(0.14, Math.max(0.0, detourRatio - DETOUR_WEAK_RATIO) * 0.10);
        double densityPenalty = Math.min(0.10, Math.max(0.0, turnDensity - TURN_DENSITY_WEAK_LIMIT) * 0.05);
        double topologyPenalty = Math.min(0.14, (crossingCount * 0.08) + (backtrackCount * 0.035) + (zigzagChangeCount * 0.012));
        double congestionPenalty = proposal.congestionScore() >= CONGESTION_HIGH_RISK
                && proposal.straightnessScore() < STRAIGHTNESS_FLOOR ? 0.05 : 0.0;
        double penalty = Math.min(0.46, straightnessPenalty + turnPenalty + detourPenalty + densityPenalty + topologyPenalty + congestionPenalty);
        String verdict = verdict(proposal, detourRatio, turnDensity, backtrackCount, crossingCount, zigzagChangeCount);
        double shapeScore = Math.max(0.0, Math.min(1.0, proposal.straightnessScore() - penalty + Math.min(0.12, 1.0 / detourRatio * 0.10)));
        return new RouteShapeAnalysis("route-shape-analysis/v1", verdict, penalty, detourRatio, turnDensity, backtrackCount, crossingCount, zigzagChangeCount, shapeScore, reasons);
    }

    private static String verdict(RouteProposal proposal,
                                  double detourRatio,
                                  double turnDensity,
                                  int backtrackCount,
                                  int crossingCount,
                                  int zigzagChangeCount) {
        if (proposal.stopOrder().size() > 1
                && (proposal.straightnessScore() < STRAIGHTNESS_REJECT_FLOOR
                || proposal.straightnessScore() < MULTI_ORDER_STRAIGHTNESS_REJECT_FLOOR
                || proposal.turnCount() > TURN_COUNT_REJECT_LIMIT
                || proposal.turnCount() > multiOrderTurnRejectLimit(proposal.stopOrder().size())
                || detourRatio > DETOUR_REJECT_RATIO
                || turnDensity > TURN_DENSITY_REJECT_LIMIT
                || crossingCount > 0)) {
            return "REJECT_SHAPE";
        }
        if (proposal.stopOrder().size() > 1
                && (proposal.straightnessScore() < MULTI_ORDER_STRAIGHTNESS_WEAK_FLOOR
                || proposal.turnCount() > MULTI_ORDER_TURN_WEAK_LIMIT
                || detourRatio > DETOUR_WEAK_RATIO
                || turnDensity > TURN_DENSITY_WEAK_LIMIT
                || (backtrackCount > 1 && proposal.straightnessScore() < 0.68)
                || (zigzagChangeCount > Math.max(2, proposal.stopOrder().size()) && proposal.straightnessScore() < 0.72)
                || (proposal.congestionScore() >= CONGESTION_SELECTED_REJECT_RISK && proposal.straightnessScore() < 0.70))) {
            return "WEAK_SHAPE";
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
        if (!candidate.driverId().equals(dominated.driverId())) {
            return false;
        }
        if (!sameOrderSet(candidate, dominated)) {
            return false;
        }
        RouteShapeAnalysis candidateAnalysis = analyze(candidate);
        RouteShapeAnalysis dominatedAnalysis = analyze(dominated);
        boolean noWorse = candidate.routeCost() <= dominated.routeCost() + 1e-9
                && candidate.totalTravelTimeSeconds() <= dominated.totalTravelTimeSeconds() + 1e-9
                && candidate.turnCount() <= dominated.turnCount()
                && candidate.straightnessScore() + 1e-9 >= dominated.straightnessScore()
                && candidate.congestionScore() <= dominated.congestionScore() + 1e-9
                && candidateAnalysis.detourRatio() <= dominatedAnalysis.detourRatio() + 1e-9
                && candidateAnalysis.crossingCount() <= dominatedAnalysis.crossingCount()
                && candidateAnalysis.backtrackCount() <= dominatedAnalysis.backtrackCount();
        boolean materiallyBetter = candidate.routeCost() < dominated.routeCost() - 25.0
                || candidate.totalTravelTimeSeconds() < dominated.totalTravelTimeSeconds() - 10.0
                || candidate.turnCount() < dominated.turnCount()
                || candidate.straightnessScore() > dominated.straightnessScore() + 0.03
                || candidateAnalysis.detourRatio() + 0.12 < dominatedAnalysis.detourRatio()
                || candidateAnalysis.penalty() + 0.03 < dominatedAnalysis.penalty();
        return noWorse && materiallyBetter;
    }

    public static List<String> reasons(RouteProposal proposal) {
        if (proposal == null || !proposal.geometryAvailable()) {
            return List.of();
        }
        RouteShapeAnalysis analysis = analyze(proposal);
        return analysis.reasons();
    }

    private static List<String> reasons(RouteProposal proposal,
                                        double detourRatio,
                                        double turnDensity,
                                        int backtrackCount,
                                        int crossingCount,
                                        int zigzagChangeCount) {
        List<String> reasons = new ArrayList<>();
        if (proposal.straightnessScore() < STRAIGHTNESS_FLOOR) {
            reasons.add("route-shape-straightness-penalty");
        }
        if (proposal.turnCount() > TURN_COUNT_SOFT_LIMIT) {
            reasons.add("route-shape-turn-penalty");
        }
        if (proposal.stopOrder().size() > 1 && proposal.turnCount() > MULTI_ORDER_TURN_WEAK_LIMIT) {
            reasons.add("route-shape-weak-turn-count");
        }
        if (proposal.stopOrder().size() > 1 && proposal.straightnessScore() < MULTI_ORDER_STRAIGHTNESS_WEAK_FLOOR) {
            reasons.add("route-shape-weak-straightness");
        }
        if (proposal.stopOrder().size() > 1
                && proposal.congestionScore() >= CONGESTION_SELECTED_REJECT_RISK
                && proposal.straightnessScore() < 0.70) {
            reasons.add("route-shape-weak-congestion");
        }
        if (proposal.congestionScore() >= CONGESTION_HIGH_RISK && proposal.straightnessScore() < STRAIGHTNESS_FLOOR) {
            reasons.add("route-shape-congestion-zigzag-penalty");
        }
        if (detourRatio > DETOUR_WEAK_RATIO) {
            reasons.add("route-shape-detour-penalty");
        }
        if (turnDensity > TURN_DENSITY_WEAK_LIMIT) {
            reasons.add("route-shape-turn-density-penalty");
        }
        if (crossingCount > 0) {
            reasons.add("route-shape-crossing-risk");
        }
        if (backtrackCount > 1 && proposal.straightnessScore() < 0.68) {
            reasons.add("route-shape-backtrack-risk");
        }
        if (zigzagChangeCount > Math.max(2, proposal.stopOrder().size()) && proposal.straightnessScore() < 0.72) {
            reasons.add("route-shape-zigzag-bearing-change");
        }
        return List.copyOf(reasons);
    }

    private static double detourRatio(RouteProposal proposal) {
        if (proposal.totalDistanceMeters() <= 0.0 || proposal.legs().isEmpty()) {
            return 1.0;
        }
        double legMeters = proposal.legs().stream()
                .mapToDouble(LegRouteVector::distanceMeters)
                .sum();
        if (legMeters <= 0.0) {
            return 1.0;
        }
        return Math.max(1.0, proposal.totalDistanceMeters() / legMeters);
    }

    private static double turnDensity(RouteProposal proposal) {
        if (proposal.totalDistanceMeters() <= 0.0) {
            return 0.0;
        }
        return proposal.turnCount() / Math.max(0.1, proposal.totalDistanceMeters() / 1000.0);
    }

    private static int backtrackCount(List<LegRouteVector> legs) {
        int count = 0;
        for (int index = 1; index < legs.size(); index++) {
            if (bearingDelta(legs.get(index - 1).bearingMeanDeg(), legs.get(index).bearingMeanDeg()) >= 145.0) {
                count++;
            }
        }
        return count;
    }

    private static int zigzagChangeCount(List<LegRouteVector> legs) {
        int count = 0;
        for (int index = 2; index < legs.size(); index++) {
            double previous = signedBearingDelta(legs.get(index - 2).bearingMeanDeg(), legs.get(index - 1).bearingMeanDeg());
            double current = signedBearingDelta(legs.get(index - 1).bearingMeanDeg(), legs.get(index).bearingMeanDeg());
            if (Math.abs(previous) >= 45.0 && Math.abs(current) >= 45.0 && Math.signum(previous) != Math.signum(current)) {
                count++;
            }
        }
        return count;
    }

    private static int crossingCount(List<LegRouteVector> legs) {
        return 0;
    }

    private static double bearingDelta(double left, double right) {
        double delta = Math.abs(left - right) % 360.0;
        return delta > 180.0 ? 360.0 - delta : delta;
    }

    private static double signedBearingDelta(double left, double right) {
        double delta = (right - left + 540.0) % 360.0 - 180.0;
        return delta == -180.0 ? 180.0 : delta;
    }

    private static boolean sameOrderSet(RouteProposal left, RouteProposal right) {
        return new java.util.HashSet<>(left.stopOrder()).equals(new java.util.HashSet<>(right.stopOrder()));
    }

    private static int multiOrderTurnRejectLimit(int stopCount) {
        return Math.min(TURN_COUNT_REJECT_LIMIT, (8 * stopCount) + 6);
    }
}
