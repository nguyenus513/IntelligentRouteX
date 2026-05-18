package com.routechain.v2.seedimprovement;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class MlPdDestroyPolicy {
    private final PdOrderImpactAnalyzer impactAnalyzer;
    private final Map<String, Double> rewards = new HashMap<>();

    public MlPdDestroyPolicy() {
        this(new PdOrderImpactAnalyzer());
    }

    public MlPdDestroyPolicy(PdOrderImpactAnalyzer impactAnalyzer) {
        this.impactAnalyzer = impactAnalyzer == null ? new PdOrderImpactAnalyzer() : impactAnalyzer;
    }

    public List<PdOrderImpact> rankOrders(PdSeedState seed, int round) {
        return impactAnalyzer.rankBadOrders(seed).stream()
                .map(impact -> new PdOrderImpact(
                        impact.orderId(),
                        impact.routeId(),
                        impact.detourContributionKm(),
                        impact.spreadKm(),
                        impact.routeDistancePerOrderKm(),
                        score(impact, seed, round)))
                .sorted(Comparator.comparingDouble(PdOrderImpact::score).reversed())
                .toList();
    }

    public int chooseDestroySize(PdSeedState seed, PdLnsMode mode) {
        int explicit = mode.destroySize();
        if (explicit > 0) {
            return explicit;
        }
        int assigned = seed == null ? 0 : Math.max(1, seed.assignedCount());
        if (assigned >= 18) {
            return 4;
        }
        if (assigned >= 10) {
            return 3;
        }
        return 2;
    }

    public void updateReward(List<String> orderIds, double reward) {
        if (orderIds == null) {
            return;
        }
        for (String orderId : orderIds) {
            rewards.merge(orderId, reward, (oldValue, next) -> oldValue * 0.70 + next * 0.30);
        }
    }

    public double reward(String orderId) {
        return rewards.getOrDefault(orderId, 0.0);
    }

    private double score(PdOrderImpact impact, PdSeedState seed, int round) {
        double detour = impact.detourContributionKm();
        double route = impact.routeDistancePerOrderKm();
        double spread = impact.spreadKm();
        double nearOtherRoute = nearOtherRouteScore(seed, impact.orderId(), impact.routeId());
        double exploration = ((Math.abs((impact.orderId() + round).hashCode()) % 100) / 100.0) * 0.15;
        double historical = reward(impact.orderId()) * 0.10;
        return round(detour * 0.30 + nearOtherRoute * 0.20 + route * 0.15 + spread * 0.10 + exploration + historical);
    }

    private double nearOtherRouteScore(PdSeedState seed, String orderId, String routeId) {
        if (seed == null) {
            return 0.0;
        }
        PdStop pickup = null;
        PdStop dropoff = null;
        for (PdRouteState route : seed.routes()) {
            for (PdStop stop : route.stops()) {
                if (!stop.orderId().equals(orderId)) {
                    continue;
                }
                if (stop.type() == PdStop.PdStopType.PICKUP) {
                    pickup = stop;
                } else if (stop.type() == PdStop.PdStopType.DROPOFF) {
                    dropoff = stop;
                }
            }
        }
        if (pickup == null || dropoff == null) {
            return 0.0;
        }
        double best = 0.0;
        for (PdRouteState route : seed.routes()) {
            if (route.routeId().equals(routeId)) {
                continue;
            }
            for (PdStop stop : route.stops()) {
                double proximity = Math.max(0.0, 10.0 - haversineKm(pickup.lat(), pickup.lng(), stop.lat(), stop.lng()))
                        + Math.max(0.0, 10.0 - haversineKm(dropoff.lat(), dropoff.lng(), stop.lat(), stop.lng()));
                best = Math.max(best, proximity);
            }
        }
        return best;
    }

    private double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double radius = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
