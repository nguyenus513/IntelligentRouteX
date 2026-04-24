package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.ArrayList;
import java.util.List;

public final class BundleValidator {
    private final RouteChainDispatchV2Properties properties;

    public BundleValidator(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public BundleCandidate validate(BundleCandidate candidate, BundleContext context) {
        List<String> degradeReasons = new ArrayList<>(candidate.degradeReasons());
        if (candidate.orderIds().size() < properties.getBundle().getMinSize()) {
            degradeReasons.add("bundle-size-below-minimum");
        }
        if (candidate.orderIds().size() > properties.getBundle().getMaxSize()) {
            degradeReasons.add("bundle-size-exceeds-limit");
        }
        if (candidate.orderIds().size() != candidate.orderIds().stream().distinct().count()) {
            degradeReasons.add("bundle-contains-duplicate-orders");
        }
        if (!context.hasConnectedSupport(candidate.orderIds())) {
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
}
