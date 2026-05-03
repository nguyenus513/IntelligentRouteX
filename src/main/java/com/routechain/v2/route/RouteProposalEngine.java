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
            for (List<String> stopOrder : recoveryStopOrders(driverCandidate, context, etaLegCache)) {
                generated.add(candidate(driverCandidate, pickupAnchor, RouteProposalSource.HEURISTIC_SAFE, stopOrder, context, etaLegCache));
            }
            for (List<String> stopOrder : beautyStopOrders(driverCandidate, context)) {
                generated.add(candidate(driverCandidate, pickupAnchor, RouteProposalSource.BEAUTY_CORRIDOR, stopOrder, context, etaLegCache));
            }
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
            case ACTIVE_ROUTE_INSERTION -> List.of("active-route-insertion-proposal");
            case BEAUTY_CORRIDOR -> List.of("route-beauty-corridor-variant", "route-beauty-low-zigzag-priority");
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

    private List<List<String>> recoveryStopOrders(DriverCandidate driverCandidate,
                                                  DispatchCandidateContext context,
                                                  EtaLegCache etaLegCache) {
        List<String> remaining = remainingOrders(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), context);
        if (remaining.size() < 2 || remaining.size() > 3) {
            return List.of();
        }
        List<List<String>> alternatives = new ArrayList<>();
        List<String> reversed = new ArrayList<>(remaining);
        java.util.Collections.reverse(reversed);
        alternatives.add(prefixed(driverCandidate.anchorOrderId(), reversed));
        alternatives.add(prefixed(driverCandidate.anchorOrderId(), nearestNeighborRemaining(driverCandidate.anchorOrderId(), remaining, context, etaLegCache)));
        return alternatives.stream()
                .distinct()
                .toList();
    }

    private List<List<String>> beautyStopOrders(DriverCandidate driverCandidate, DispatchCandidateContext context) {
        List<String> remaining = remainingOrders(driverCandidate.bundleId(), driverCandidate.anchorOrderId(), context);
        if (remaining.size() < 2) {
            return List.of();
        }
        List<String> corridorOrdered = remaining.stream()
                .sorted(Comparator.comparingDouble((String orderId) -> corridorProjection(context.order(driverCandidate.anchorOrderId()), context.order(orderId)))
                        .thenComparing(orderId -> context.order(orderId).readyAt())
                        .thenComparing(orderId -> orderId))
                .toList();
        return List.of(prefixed(driverCandidate.anchorOrderId(), corridorOrdered));
    }

    private double corridorProjection(Order anchorOrder, Order candidateOrder) {
        if (anchorOrder == null || candidateOrder == null) {
            return Double.MAX_VALUE;
        }
        double anchorDx = anchorOrder.dropoffPoint().latitude() - anchorOrder.pickupPoint().latitude();
        double anchorDy = anchorOrder.dropoffPoint().longitude() - anchorOrder.pickupPoint().longitude();
        double candidateDx = candidateOrder.pickupPoint().latitude() - anchorOrder.pickupPoint().latitude();
        double candidateDy = candidateOrder.pickupPoint().longitude() - anchorOrder.pickupPoint().longitude();
        double norm = Math.max(1e-6, Math.sqrt(anchorDx * anchorDx + anchorDy * anchorDy));
        double projection = (candidateDx * anchorDx + candidateDy * anchorDy) / norm;
        double crossTrack = Math.abs(candidateDx * anchorDy - candidateDy * anchorDx) / norm;
        return projection + 2.0 * crossTrack;
    }

    private List<String> nearestNeighborRemaining(String anchorOrderId,
                                                  List<String> remaining,
                                                  DispatchCandidateContext context,
                                                  EtaLegCache etaLegCache) {
        List<String> ordered = new ArrayList<>();
        List<String> candidates = new ArrayList<>(remaining);
        String currentOrderId = anchorOrderId;
        while (!candidates.isEmpty()) {
            Order current = context.order(currentOrderId);
            String fromOrderId = currentOrderId;
            String nextOrderId = candidates.stream()
                    .min(Comparator.comparingDouble((String orderId) -> etaLegCache.getOrEstimate(
                                    current == null ? context.order(orderId).pickupPoint() : current.dropoffPoint(),
                                    context.order(orderId).pickupPoint(),
                                    "route-proposal-recovery-nearest",
                                    fromOrderId + "->" + orderId)
                            .etaMinutes())
                            .thenComparing(orderId -> orderId))
                    .orElse(candidates.getFirst());
            ordered.add(nextOrderId);
            candidates.remove(nextOrderId);
            currentOrderId = nextOrderId;
        }
        return List.copyOf(ordered);
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
        List<Order> pickupOrders = stopOrder.stream()
                .map(context::order)
                .filter(Objects::nonNull)
                .toList();
        if (pickupOrders.isEmpty()) {
            return new RouteProjection(totalMinutes, List.of());
        }
        for (int index = 0; index < pickupOrders.size() - 1; index++) {
            Order current = pickupOrders.get(index);
            Order next = pickupOrders.get(index + 1);
            EtaEstimate pickupTransitionEta = etaLegCache.getOrEstimate(
                    current.pickupPoint(),
                    next.pickupPoint(),
                    "route-proposal-pickup-transition",
                    current.orderId() + ":pickup->" + next.orderId() + ":pickup");
            totalMinutes += pickupTransitionEta.etaMinutes();
            degradeReasons.addAll(pickupTransitionEta.degradeReasons());
        }
        List<Order> deliveryOrders = deliveryOrder(pickupOrders, etaLegCache);
        Order lastPickup = pickupOrders.getLast();
        for (int index = 0; index < deliveryOrders.size(); index++) {
            Order currentDelivery = deliveryOrders.get(index);
            EtaEstimate deliveryEta;
            if (index == 0) {
                deliveryEta = etaLegCache.getOrEstimate(
                        lastPickup.pickupPoint(),
                        currentDelivery.dropoffPoint(),
                        "route-proposal-first-delivery",
                        lastPickup.orderId() + ":pickup->" + currentDelivery.orderId() + ":dropoff");
            } else {
                Order previousDelivery = deliveryOrders.get(index - 1);
                deliveryEta = etaLegCache.getOrEstimate(
                        previousDelivery.dropoffPoint(),
                        currentDelivery.dropoffPoint(),
                        "route-proposal-delivery-transition",
                        previousDelivery.orderId() + ":dropoff->" + currentDelivery.orderId() + ":dropoff");
            }
            totalMinutes += deliveryEta.etaMinutes();
            degradeReasons.addAll(deliveryEta.degradeReasons());
        }
        return new RouteProjection(totalMinutes, degradeReasons.stream().distinct().toList());
    }

    private List<Order> deliveryOrder(List<Order> pickupOrders, EtaLegCache etaLegCache) {
        if (pickupOrders.size() <= 1) {
            return List.copyOf(pickupOrders);
        }
        List<Order> remaining = new ArrayList<>(pickupOrders);
        List<Order> ordered = new ArrayList<>(pickupOrders.size());
        Order lastPickup = pickupOrders.getLast();
        while (!remaining.isEmpty()) {
            Order fromOrder = ordered.isEmpty() ? lastPickup : ordered.getLast();
            boolean fromPickup = ordered.isEmpty();
            Order next = remaining.stream()
                    .min(Comparator.comparingDouble((Order candidate) -> etaLegCache.getOrEstimate(
                                    fromPickup ? fromOrder.pickupPoint() : fromOrder.dropoffPoint(),
                                    candidate.dropoffPoint(),
                                    "route-proposal-delivery-order",
                                    (fromPickup ? fromOrder.orderId() + ":pickup" : fromOrder.orderId() + ":dropoff")
                                            + "->" + candidate.orderId() + ":dropoff")
                            .etaMinutes())
                            .thenComparing(Order::orderId))
                    .orElse(remaining.getFirst());
            ordered.add(next);
            remaining.remove(next);
        }
        return List.copyOf(ordered);
    }

    private record RouteProjection(
            double projectedCompletionEtaMinutes,
            List<String> degradeReasons) {
    }
}
