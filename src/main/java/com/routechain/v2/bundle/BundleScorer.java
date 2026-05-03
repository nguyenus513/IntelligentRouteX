package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Order;
import com.routechain.v2.optimizer.HybridOptimizerObjective;

import java.util.List;
import java.util.Map;

public final class BundleScorer {
    private final RouteChainDispatchV2Properties properties;

    public BundleScorer(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public BundleCandidate score(BundleCandidate candidate, BundleContext context) {
        List<Order> orders = context.orders(candidate.orderIds());
        double pairSupport = context.averagePairSupport(candidate.orderIds());
        double score = HybridOptimizerObjective.bundleScore(
                pairSupport,
                orders,
                boundarySupport(candidate, context),
                candidate.family() == BundleFamily.BOUNDARY_CROSS,
                candidate.family() == BundleFamily.URGENT_COMPANION,
                properties.getPair().getReadyGapMinutesThreshold());
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
                score,
                candidate.feasible(),
                candidate.degradeReasons());
    }

    private double boundarySupport(BundleCandidate candidate, BundleContext context) {
        if (!candidate.boundaryCross()) {
            return 0.0;
        }
        BoundaryExpansion expansion = context.expansionsByClusterId().get(candidate.clusterId());
        if (expansion == null) {
            return 0.0;
        }
        return expansion.supportScoreByOrder().entrySet().stream()
                .filter(entry -> candidate.acceptedBoundaryOrderIds().contains(entry.getKey()))
                .mapToDouble(Map.Entry::getValue)
                .average()
                .orElse(0.0);
    }
}
