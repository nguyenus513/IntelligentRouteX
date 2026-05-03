package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class BundleValidator {
    private final RouteChainDispatchV2Properties properties;

    public BundleValidator(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public BundleCandidate validate(BundleCandidate candidate, BundleContext context) {
        List<String> degradeReasons = new ArrayList<>(candidate.degradeReasons());
        if (candidate.orderIds().size() < properties.getBundle().getMinSize()
                && candidate.family() != BundleFamily.URGENT_SINGLE_FALLBACK) {
            degradeReasons.add("bundle-size-below-minimum");
        }
        if (candidate.orderIds().size() > properties.getBundle().getMaxSize()) {
            degradeReasons.add("bundle-size-exceeds-limit");
        }
        if (candidate.orderIds().size() != candidate.orderIds().stream().distinct().count()) {
            degradeReasons.add("bundle-contains-duplicate-orders");
        }
        if (!context.hasConnectedSupport(candidate.orderIds()) && !hasMlSafeGeometrySupport(candidate, context)) {
            degradeReasons.add("bundle-lacks-connected-support");
        }
        if (candidate.boundaryCross()) {
            boolean hasBoundaryOrder = !candidate.acceptedBoundaryOrderIds().isEmpty();
            if (!hasBoundaryOrder) {
                degradeReasons.add("boundary-cross-missing-accepted-boundary-order");
            }
        }
        if (candidate.family() == BundleFamily.URGENT_COMPANION) {
            long urgentCount = candidate.orderIds().stream().map(context::order).filter(order -> order != null && order.urgent()).count();
            if (urgentCount != 1) {
                degradeReasons.add("urgent-companion-requires-single-urgent-order");
            }
        }
        return new BundleCandidate(
                candidate.schemaVersion(),
                candidate.bundleId(),
                candidate.proposalSource(),
                candidate.family(),
                candidate.clusterId(),
                candidate.boundaryCross(),
                candidate.acceptedBoundaryOrderIds(),
                candidate.orderIds(),
                candidate.orderSetSignature(),
                candidate.seedOrderId(),
                candidate.corridorSignature(),
                candidate.score(),
                degradeReasons.isEmpty(),
                List.copyOf(degradeReasons));
    }

    private boolean hasMlSafeGeometrySupport(BundleCandidate candidate, BundleContext context) {
        if (candidate.proposalSource() != BundleProposalSource.GREEDRL_PROPOSAL || candidate.orderIds().size() <= 1) {
            return false;
        }
        List<String> sorted = candidate.orderIds().stream().sorted().toList();
        ArrayDeque<String> queue = new ArrayDeque<>();
        Set<String> visited = new HashSet<>();
        queue.add(sorted.getFirst());
        visited.add(sorted.getFirst());
        while (!queue.isEmpty()) {
            String current = queue.removeFirst();
            for (String candidateOrderId : sorted) {
                if (!visited.contains(candidateOrderId)
                        && (context.hasSupport(current, candidateOrderId) || isMlSafeGeometryPair(context.order(current), context.order(candidateOrderId)))) {
                    visited.add(candidateOrderId);
                    queue.add(candidateOrderId);
                }
            }
        }
        return visited.size() == sorted.size();
    }

    private boolean isMlSafeGeometryPair(Order left, Order right) {
        if (left == null || right == null) {
            return false;
        }
        double mlSafePickupKm = Math.max(properties.getPair().getPickupDistanceKmThreshold() * 2.0, 5.0);
        return distanceKm(left.pickupPoint(), right.pickupPoint()) <= mlSafePickupKm;
    }

    private double distanceKm(GeoPoint left, GeoPoint right) {
        double latKm = (left.latitude() - right.latitude()) * 111.0;
        double lonKm = (left.longitude() - right.longitude()) * 111.0
                * Math.cos(Math.toRadians((left.latitude() + right.latitude()) / 2.0));
        return Math.sqrt(latKm * latKm + lonKm * lonKm);
    }
}
