package com.routechain.v2.route;

import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.context.EtaEstimate;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public final class RouteProposalEngine {

    public List<RouteProposalCandidate> generate(List<DriverCandidate> driverCandidates,
                                                 List<PickupAnchor> pickupAnchors,
                                                 DispatchCandidateContext context,
                                                 EtaLegCache etaLegCache) {
        java.util.Map<String, PickupAnchor> anchorByBundleAndOrder = pickupAnchors.stream()
                .collect(java.util.stream.Collectors.toMap(
                        anchor -> anchor.bundleId() + "|" + anchor.anchorOrderId(),
                        anchor -> anchor,
                        (left, right) -> left));
        List<RouteProposalCandidate> generated = new ArrayList<>();
        for (DriverCandidate driverCandidate : driverCandidates.stream()
                .sorted(Comparator.comparing(DriverCandidate::bundleId)
                        .thenComparing(DriverCandidate::anchorOrderId)
                        .thenComparing(DriverCandidate::driverId))
                .toList()) {
            PickupAnchor pickupAnchor = anchorByBundleAndOrder.get(driverCandidate.bundleId() + "|" + driverCandidate.anchorOrderId());
            if (pickupAnchor == null) {
                continue;
            }
            generated.add(candidate(driverCandidate, pickupAnchor, RouteProposalSource.HEURISTIC_FAST, fastStopOrder(driverCandidate, context, etaLegCache), context, etaLegCache));
            generated.add(candidate(driverCandidate, pickupAnchor, RouteProposalSource.HEURISTIC_SAFE, safeStopOrder(driverCandidate, context), context, etaLegCache));
            generated.add(candidate(driverCandidate, pickupAnchor, RouteProposalSource.FALLBACK_SIMPLE, fallbackStopOrder(driverCandidate, context), context, etaLegCache));
        }
        return List.copyOf(generated);
    }

    public RouteProposalCandidate externalCandidate(DriverCandidate driverCandidate,
                                                    PickupAnchor pickupAnchor,
                                                    RouteProposalSource source,
                                                    List<String> stopOrder,
                                                    double projectedPickupEtaMinutes,
                                                    double projectedCompletionEtaMinutes,
                                                    List<String> reasons,
                                                    List<String> degradeReasons) {
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey(driverCandidate.bundleId(), pickupAnchor.anchorOrderId(), driverCandidate.driverId());
        RouteProposal proposal = baseProposal(
                driverCandidate,
                pickupAnchor,
                source,
                stopOrder,
                projectedPickupEtaMinutes,
                projectedCompletionEtaMinutes,
                false,
                reasons,
                degradeReasons);
        return new RouteProposalCandidate(
                proposal,
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(
                        tupleKey,
                        source,
                        stopOrderSignature(stopOrder),
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        source == RouteProposalSource.FALLBACK_SIMPLE ? 0.05 : 0.0,
                        List.of()));
    }

    public static String stopOrderSignature(List<String> stopOrder) {
        return String.join(">", stopOrder);
    }

    private RouteProposalCandidate candidate(DriverCandidate driverCandidate,
                                             PickupAnchor pickupAnchor,
                                             RouteProposalSource source,
                                             List<String> stopOrder,
                                             DispatchCandidateContext context,
                                             EtaLegCache etaLegCache) {
        Driver driver = context.driver(driverCandidate.driverId());
        Order anchorOrder = context.order(pickupAnchor.anchorOrderId());
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey(driverCandidate.bundleId(), pickupAnchor.anchorOrderId(), driverCandidate.driverId());
        if (driver == null || anchorOrder == null) {
            RouteProposal proposal = baseProposal(driverCandidate, pickupAnchor, source, stopOrder, 0.0, 0.0, false, List.of("route-proposal-missing-anchor-or-driver"), List.of());
            return new RouteProposalCandidate(
                    proposal,
                    tupleKey,
                    pickupAnchor,
                    driverCandidate,
                    new RouteProposalTrace(tupleKey, source, stopOrderSignature(stopOrder), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, source == RouteProposalSource.FALLBACK_SIMPLE ? 0.05 : 0.0, List.of("route-proposal-missing-anchor-or-driver")));
        }
        EtaEstimate pickupEstimate = etaLegCache.getOrEstimate(
                driver.currentLocation(),
                anchorOrder.pickupPoint(),
                "route-proposal-driver-pickup",
                driver.driverId() + "->" + pickupAnchor.anchorOrderId());
        RouteProjection projection = projectRoute(stopOrder, context, etaLegCache, pickupEstimate.etaMinutes());
        List<String> reasons = switch (source) {
            case HEURISTIC_FAST -> List.of("fast-pickup-priority");
            case HEURISTIC_SAFE -> List.of("safe-support-priority");
            case FALLBACK_SIMPLE -> List.of("fallback-anchor-first");
            case ML_PROPOSAL -> List.of("routefinder-ml-proposal");
            case ML_REFINED -> List.of("routefinder-ml-refined");
        };
        List<String> degradeReasons = new ArrayList<>(pickupEstimate.degradeReasons());
        degradeReasons.addAll(projection.degradeReasons());
        RouteProposal proposal = baseProposal(
                driverCandidate,
                pickupAnchor,
                source,
                stopOrder,
                pickupEstimate.etaMinutes(),
                projection.projectedCompletionEtaMinutes(),
                false,
                reasons,
                degradeReasons.stream().distinct().toList());
        return new RouteProposalCandidate(
                proposal,
                tupleKey,
                pickupAnchor,
                driverCandidate,
                new RouteProposalTrace(tupleKey, source, stopOrderSignature(stopOrder), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, source == RouteProposalSource.FALLBACK_SIMPLE ? 0.05 : 0.0, List.of()));
    }

    private RouteProposal baseProposal(DriverCandidate driverCandidate,
                                       PickupAnchor pickupAnchor,
                                       RouteProposalSource source,
                                       List<String> stopOrder,
                                       double projectedPickupEtaMinutes,
                                       double projectedCompletionEtaMinutes,
                                       boolean feasible,
                                       List<String> reasons,
                                       List<String> degradeReasons) {
        return new RouteProposal(
                "route-proposal/v1",
                "%s|%s|%s|%s|%s".formatted(
                        driverCandidate.bundleId(),
                        pickupAnchor.anchorOrderId(),
                        driverCandidate.driverId(),
                        source.name(),
                        stopOrderSignature(stopOrder)),
                driverCandidate.bundleId(),
                pickupAnchor.anchorOrderId(),
                driverCandidate.driverId(),
                source,
                List.copyOf(stopOrder),
                projectedPickupEtaMinutes,
                projectedCompletionEtaMinutes,
                0.0,
                feasible,
                List.copyOf(reasons),
                List.copyOf(degradeReasons));
    }

    private List<String> fastStopOrder(DriverCandidate driverCandidate,
                                       DispatchCandidateContext context,
                                       EtaLegCache etaLegCache) {
        List<String> remaining = remainingOrders(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), context);
        Order anchorOrder = context.order(driverCandidate.anchorOrderId());
        return prefixed(driverCandidate.anchorOrderId(), remaining.stream()
                .sorted(Comparator.comparingDouble((String orderId) -> etaLegCache.getOrEstimate(
                                anchorOrder.pickupPoint(),
                                context.order(orderId).pickupPoint(),
                                "route-proposal-fast",
                                driverCandidate.anchorOrderId() + "->" + orderId)
                        .etaMinutes())
                        .thenComparing(orderId -> context.order(orderId).readyAt())
                        .thenComparing(orderId -> orderId))
                .toList());
    }

    private List<String> safeStopOrder(DriverCandidate driverCandidate, DispatchCandidateContext context) {
        return prefixed(driverCandidate.anchorOrderId(), remainingOrders(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), context).stream()
                .sorted(Comparator.comparing((String orderId) -> context.isAcceptedBoundaryOrder(driverCandidate.bundleId(), orderId))
                        .thenComparing(Comparator.comparingDouble((String orderId) -> context.pairSupport(driverCandidate.anchorOrderId(), orderId)).reversed())
                        .thenComparing(orderId -> context.order(orderId).readyAt())
                        .thenComparing(orderId -> orderId))
                .toList());
    }

    private List<String> fallbackStopOrder(DriverCandidate driverCandidate, DispatchCandidateContext context) {
        return prefixed(driverCandidate.anchorOrderId(), remainingOrders(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), context).stream()
                .sorted()
                .toList());
    }

    private List<String> prefixed(String anchorOrderId, List<String> remaining) {
        List<String> stopOrder = new ArrayList<>();
        stopOrder.add(anchorOrderId);
        stopOrder.addAll(remaining);
        return List.copyOf(stopOrder);
    }

    private List<String> remainingOrders(String bundleId, String anchorOrderId, DispatchCandidateContext context) {
        return context.bundle(bundleId).orderIds().stream()
                .filter(orderId -> !Objects.equals(orderId, anchorOrderId))
                .toList();
    }

    private RouteProjection projectRoute(List<String> stopOrder,
                                         DispatchCandidateContext context,
                                         EtaLegCache etaLegCache,
                                         double startingPickupEtaMinutes) {
        double totalMinutes = startingPickupEtaMinutes;
        List<String> degradeReasons = new ArrayList<>();
        for (int index = 0; index < stopOrder.size(); index++) {
            Order current = context.order(stopOrder.get(index));
            if (current == null) {
                continue;
            }
            EtaEstimate serviceEta = etaLegCache.getOrEstimate(
                    current.pickupPoint(),
                    current.dropoffPoint(),
                    "route-proposal-service",
                    current.orderId() + "-service");
            totalMinutes += serviceEta.etaMinutes();
            degradeReasons.addAll(serviceEta.degradeReasons());
            if (index < stopOrder.size() - 1) {
                Order next = context.order(stopOrder.get(index + 1));
                if (next != null) {
                    EtaEstimate transitionEta = etaLegCache.getOrEstimate(
                            current.dropoffPoint(),
                            next.pickupPoint(),
                            "route-proposal-transition",
                            current.orderId() + "->" + next.orderId());
                    totalMinutes += transitionEta.etaMinutes();
                    degradeReasons.addAll(transitionEta.degradeReasons());
                }
            }
        }
        return new RouteProjection(totalMinutes, degradeReasons.stream().distinct().toList());
    }

    private record RouteProjection(
            double projectedCompletionEtaMinutes,
            List<String> degradeReasons) {
    }
}
