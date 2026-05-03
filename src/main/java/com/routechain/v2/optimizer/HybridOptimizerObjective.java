package com.routechain.v2.optimizer;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteShapeAnalysis;
import com.routechain.v2.route.RouteShapeQuality;
import com.routechain.v2.scenario.RobustUtility;

import java.time.Duration;
import java.util.List;

public final class HybridOptimizerObjective {
    private HybridOptimizerObjective() {
    }

    public static double bundleScore(double pairSupport,
                                     List<Order> orders,
                                     double boundarySupport,
                                     boolean boundaryCross,
                                     boolean urgencyFamily,
                                     int readyGapThresholdMinutes) {
        double pickupCompactness = pickupCompactness(orders);
        double readyCompatibility = readyCompatibility(orders, readyGapThresholdMinutes);
        double corridorFit = corridorFit(orders);
        double freshnessGuard = freshnessGuard(orders);
        double landingCompatibility = Math.max(0.2, 1.0 - (Math.abs(orders.size() - 2) * 0.1));
        double coverageLift = Math.min(0.18, Math.max(0, orders.size() - 1) * 0.06);
        double urgencyBonus = urgencyFamily ? 0.09 : (orders.stream().anyMatch(Order::urgent) ? 0.04 : 0.0);
        double boundaryPenalty = boundaryCross ? Math.max(0.0, 0.25 - boundarySupport) : 0.0;
        double tailRiskPenalty = Math.max(0.0, 1.0 - Math.min(readyCompatibility, freshnessGuard)) * 0.16;
        return clamp(
                0.26 * pairSupport
                        + 0.17 * pickupCompactness
                        + 0.16 * readyCompatibility
                        + 0.16 * corridorFit
                        + 0.11 * freshnessGuard
                        + 0.08 * landingCompatibility
                        + coverageLift
                        + urgencyBonus
                        - boundaryPenalty
                        - tailRiskPenalty);
    }

    public static double anchorScore(Order anchorOrder,
                                     List<Order> bundleOrders,
                                     List<Driver> availableDrivers,
                                     boolean boundaryCross,
                                     boolean acceptedBoundaryOrder) {
        double readySlack = readySlack(anchorOrder, bundleOrders);
        double pickupCentrality = anchorPickupCentrality(anchorOrder, bundleOrders);
        double dropoffCorridorFit = anchorDropoffCorridorFit(anchorOrder, bundleOrders);
        double courierProximity = courierProximity(anchorOrder, availableDrivers);
        double detourRisk = Math.max(0.0, 1.0 - ((pickupCentrality + dropoffCorridorFit) / 2.0));
        double trafficRisk = clamp(detourRisk * 0.65 + Math.max(0.0, 1.0 - courierProximity) * 0.35);
        double urgencyBonus = anchorOrder.urgent() ? 0.06 : 0.0;
        double boundaryPenalty = (acceptedBoundaryOrder ? 0.10 : 0.0) + (boundaryCross ? 0.04 : 0.0);
        return clamp(
                0.28 * readySlack
                        + 0.22 * pickupCentrality
                        + 0.20 * courierProximity
                        + 0.17 * dropoffCorridorFit
                        + 0.08 * (1.0 - detourRisk)
                        + 0.05 * (1.0 - trafficRisk)
                        + urgencyBonus
                        - boundaryPenalty);
    }

    public static double selectorScore(RouteProposal proposal,
                                       RobustUtility robustUtility,
                                       DriverCandidate driverCandidate,
                                       DispatchCandidateContext context,
                                       double fallbackPenalty) {
        RouteShapeAnalysis routeShape = RouteShapeQuality.analyze(proposal);
        int orderCount = proposal.stopOrder().size();
        double bundleScore = context.bundleScore(proposal.bundleId());
        double readySpreadScore = clamp(1.0 - (context.readyTimeSpread(proposal.bundleId()) / 18.0));
        double pickupCompactness = context.pickupCompactness(proposal.bundleId());
        double routeBeauty = routeShape.shapeScore();
        double stability = robustUtility.stabilityScore();
        double coverageLift = Math.min(0.42, Math.max(0, orderCount - 1) * 0.11);
        double pickupEtaScore = clamp(1.0 - driverCandidate.pickupEtaMinutes() / 25.0);
        double exactMlBlend = 0.30 * robustUtility.robustUtility()
                + 0.12 * robustUtility.worstCaseValue()
                + 0.12 * proposal.routeValue()
                + 0.10 * driverCandidate.rerankScore();
        double productQuality = 0.13 * bundleScore
                + 0.08 * readySpreadScore
                + 0.07 * pickupCompactness
                + 0.10 * routeBeauty
                + 0.06 * pickupEtaScore
                + 0.04 * stability;
        double riskPenalty = routeShape.penalty()
                + Math.max(0.0, routeShape.detourRatio() - 1.35) * 0.08
                + Math.max(0.0, proposal.congestionScore() - 0.70) * 0.05
                + context.acceptedBoundaryParticipation(proposal.bundleId()) * 0.04;
        if (proposal.source() == RouteProposalSource.FALLBACK_SIMPLE) {
            riskPenalty += fallbackPenalty;
        }
        if (context.bundle(proposal.bundleId()) != null
                && context.bundle(proposal.bundleId()).boundaryCross()
                && context.acceptedBoundarySupport(proposal.bundleId()) < 0.60) {
            riskPenalty += 0.04;
        }
        return exactMlBlend + productQuality + coverageLift - riskPenalty;
    }

    public static double pickupCompactness(List<Order> orders) {
        if (orders.size() <= 1) {
            return 1.0;
        }
        double maxDistance = 0.0;
        for (Order left : orders) {
            for (Order right : orders) {
                maxDistance = Math.max(maxDistance, distance(left.pickupPoint(), right.pickupPoint()));
            }
        }
        return clamp(1.0 - maxDistance * 8.0);
    }

    public static double readyCompatibility(List<Order> orders, int readyGapThresholdMinutes) {
        if (orders.size() <= 1) {
            return 1.0;
        }
        java.time.Instant earliest = orders.stream().map(Order::readyAt).min(java.util.Comparator.naturalOrder()).orElse(java.time.Instant.EPOCH);
        java.time.Instant latest = orders.stream().map(Order::readyAt).max(java.util.Comparator.naturalOrder()).orElse(java.time.Instant.EPOCH);
        double gap = Math.max(0.0, Duration.between(earliest, latest).toMinutes());
        return clamp(1.0 - gap / Math.max(1, readyGapThresholdMinutes));
    }

    public static double corridorFit(List<Order> orders) {
        if (orders.size() <= 1) {
            return 1.0;
        }
        double meanBearing = orders.stream().mapToDouble(HybridOptimizerObjective::bearing).average().orElse(0.0);
        double meanSpread = orders.stream()
                .mapToDouble(order -> bearingDelta(meanBearing, bearing(order)))
                .average()
                .orElse(0.0);
        double dropoffSpread = dropoffSpread(orders);
        return clamp(1.0 - meanSpread / 120.0 - dropoffSpread * 4.0);
    }

    public static double freshnessGuard(List<Order> orders) {
        if (orders.isEmpty()) {
            return 0.0;
        }
        double maxPrepMinutes = orders.stream()
                .mapToDouble(order -> Math.max(0.0, Duration.between(order.createdAt(), order.readyAt()).toMinutes()))
                .max()
                .orElse(0.0);
        double promisedPressure = orders.stream()
                .mapToDouble(order -> Math.max(0.0, 35.0 - order.promisedEtaMinutes()) / 35.0)
                .average()
                .orElse(0.0);
        return clamp(1.0 - maxPrepMinutes / 45.0 - promisedPressure * 0.20);
    }

    private static double readySlack(Order anchorOrder, List<Order> bundleOrders) {
        if (bundleOrders.size() <= 1) {
            return 1.0;
        }
        double averageGap = bundleOrders.stream()
                .mapToDouble(order -> Math.abs(Duration.between(anchorOrder.readyAt(), order.readyAt()).toMinutes()))
                .average()
                .orElse(0.0);
        return clamp(1.0 - averageGap / 12.0);
    }

    private static double anchorPickupCentrality(Order anchorOrder, List<Order> bundleOrders) {
        if (bundleOrders.size() <= 1) {
            return 1.0;
        }
        double averageDistance = bundleOrders.stream()
                .filter(order -> !order.orderId().equals(anchorOrder.orderId()))
                .mapToDouble(order -> distance(anchorOrder.pickupPoint(), order.pickupPoint()))
                .average()
                .orElse(0.0);
        return clamp(1.0 - averageDistance * 9.0);
    }

    private static double anchorDropoffCorridorFit(Order anchorOrder, List<Order> bundleOrders) {
        if (bundleOrders.size() <= 1) {
            return 1.0;
        }
        double anchorBearing = bearing(anchorOrder);
        double averageDelta = bundleOrders.stream()
                .mapToDouble(order -> bearingDelta(anchorBearing, bearing(order)))
                .average()
                .orElse(0.0);
        return clamp(1.0 - averageDelta / 120.0);
    }

    private static double courierProximity(Order anchorOrder, List<Driver> availableDrivers) {
        if (availableDrivers == null || availableDrivers.isEmpty()) {
            return 0.5;
        }
        double nearestDistance = availableDrivers.stream()
                .mapToDouble(driver -> distance(driver.currentLocation(), anchorOrder.pickupPoint()))
                .min()
                .orElse(0.0);
        return clamp(1.0 - nearestDistance * 7.0);
    }

    private static double dropoffSpread(List<Order> orders) {
        double maxDistance = 0.0;
        for (Order left : orders) {
            for (Order right : orders) {
                maxDistance = Math.max(maxDistance, distance(left.dropoffPoint(), right.dropoffPoint()));
            }
        }
        return maxDistance;
    }

    private static double bearing(Order order) {
        double y = order.dropoffPoint().longitude() - order.pickupPoint().longitude();
        double x = order.dropoffPoint().latitude() - order.pickupPoint().latitude();
        return Math.toDegrees(Math.atan2(y, x));
    }

    private static double bearingDelta(double left, double right) {
        double delta = Math.abs(left - right) % 360.0;
        return delta > 180.0 ? 360.0 - delta : delta;
    }

    private static double distance(GeoPoint left, GeoPoint right) {
        double latitude = left.latitude() - right.latitude();
        double longitude = left.longitude() - right.longitude();
        return Math.sqrt((latitude * latitude) + (longitude * longitude));
    }

    private static double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }
}
