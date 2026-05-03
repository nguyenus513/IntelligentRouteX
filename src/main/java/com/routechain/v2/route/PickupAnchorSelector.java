package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Order;
import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.bundle.BundleFamily;
import com.routechain.v2.optimizer.HybridOptimizerObjective;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class PickupAnchorSelector {
    private final RouteChainDispatchV2Properties properties;

    public PickupAnchorSelector(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public List<PickupAnchor> select(List<com.routechain.v2.bundle.BundleCandidate> bundles, DispatchCandidateContext context) {
        List<PickupAnchor> anchors = new ArrayList<>();
        for (BundleCandidate bundle : bundles.stream().sorted(Comparator.comparing(BundleCandidate::bundleId)).toList()) {
            List<Order> orders = bundle.orderIds().stream()
                    .map(context::order)
                    .filter(java.util.Objects::nonNull)
                    .toList();
            List<PickupAnchor> rankedAnchors = orders.stream()
                    .map(order -> anchor(bundle, order, context, orders))
                    .sorted(Comparator.comparingDouble(PickupAnchor::score).reversed()
                            .thenComparing(PickupAnchor::anchorOrderId))
                    .limit(Math.max(1, properties.getCandidate().getMaxAnchors()))
                    .toList();
            int rank = 1;
            for (PickupAnchor anchor : rankedAnchors) {
                anchors.add(new PickupAnchor(
                        anchor.schemaVersion(),
                        anchor.bundleId(),
                        anchor.bundleOrderSetSignature(),
                        anchor.anchorOrderId(),
                        rank++,
                        anchor.score(),
                        anchor.reasons()));
            }
        }
        return List.copyOf(anchors);
    }

    private PickupAnchor anchor(BundleCandidate bundle, Order anchorOrder, DispatchCandidateContext context, List<Order> bundleOrders) {
        double score = HybridOptimizerObjective.anchorScore(
                anchorOrder,
                bundleOrders,
                context.availableDrivers(),
                bundle.family() == BundleFamily.BOUNDARY_CROSS,
                context.isAcceptedBoundaryOrder(bundle.bundleId(), anchorOrder.orderId()));
        List<String> reasons = new ArrayList<>();
        if (anchorOrder.urgent()) {
            reasons.add("urgent-anchor-boost");
        }
        if (bundle.family() == BundleFamily.BOUNDARY_CROSS
                || context.isAcceptedBoundaryOrder(bundle.bundleId(), anchorOrder.orderId())) {
            reasons.add("boundary-cross-caution");
        }
        reasons.add("hybrid-anchor-ready-corridor-proximity-score");
        return new PickupAnchor(
                "pickup-anchor/v1",
                bundle.bundleId(),
                bundle.orderSetSignature(),
                anchorOrder.orderId(),
                0,
                score,
                List.copyOf(reasons));
    }
}
