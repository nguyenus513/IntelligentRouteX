package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Order;

import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;

public final class BundleFamilyEnumerator {
    private final RouteChainDispatchV2Properties properties;

    public BundleFamilyEnumerator(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public List<BundleCandidate> enumerate(BundleSeed seed, BundleContext context) {
        List<Order> prioritizedOrders = seed.prioritizedOrderIds().stream().map(context::order).toList();
        List<Order> workingOrders = seed.workingOrderIds().stream().map(context::order).sorted(Comparator.comparing(Order::orderId)).toList();
        if (workingOrders.isEmpty()) {
            return List.of();
        }

        Order preferredSeed = prioritizedOrders.isEmpty() ? workingOrders.getFirst() : prioritizedOrders.getFirst();
        java.util.ArrayList<BundleCandidate> candidates = new java.util.ArrayList<>();
        candidates.addAll(candidateSeries(seed, BundleFamily.COMPACT_CLIQUE,
                orderedWithSeedFirst(preferredSeed, prioritizedOrders), properties.getBundle().getMaxSize(), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.CORRIDOR_CHAIN,
                corridorOrdered(preferredSeed, prioritizedOrders), Math.min(4, properties.getBundle().getMaxSize()), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.FAN_OUT_LIGHT,
                readyOrdered(preferredSeed, prioritizedOrders), Math.min(4, properties.getBundle().getMaxSize()), context));
        if (!seed.acceptedBoundaryOrderIds().isEmpty()) {
            candidates.addAll(candidateSeries(seed, BundleFamily.BOUNDARY_CROSS,
                    boundaryOrdered(preferredSeed, prioritizedOrders, seed.acceptedBoundaryOrderIds(), context), Math.min(4, properties.getBundle().getMaxSize()), context));
            candidates.addAll(candidateSeries(seed, BundleFamily.ACTIVE_ROUTE_ADDON,
                    boundaryOrdered(preferredSeed, prioritizedOrders, seed.acceptedBoundaryOrderIds(), context), Math.min(3, properties.getBundle().getMaxSize()), context));
        }
        Order urgentOrder = workingOrders.stream().filter(Order::urgent).findFirst().orElse(null);
        if (urgentOrder != null) {
            candidates.addAll(candidateSeries(seed, BundleFamily.URGENT_COMPANION,
                    urgentOrdered(urgentOrder, prioritizedOrders), Math.min(4, properties.getBundle().getMaxSize()), context));
        }
        candidates.addAll(candidateSeries(seed, BundleFamily.LANDING_VALUE_BUNDLE,
                landingValueOrdered(preferredSeed, prioritizedOrders), properties.getBundle().getMaxSize(), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.SAME_RESTAURANT,
                samePickupOrdered(preferredSeed, prioritizedOrders), Math.min(3, properties.getBundle().getMaxSize()), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.SAME_FOOD_COURT,
                pickupCellOrdered(preferredSeed, prioritizedOrders), Math.min(3, properties.getBundle().getMaxSize()), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.SAME_DELIVERY_ZONE,
                dropoffCellOrdered(preferredSeed, prioritizedOrders), Math.min(4, properties.getBundle().getMaxSize()), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.CORRIDOR,
                corridorOrdered(preferredSeed, prioritizedOrders), Math.min(4, properties.getBundle().getMaxSize()), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.NEIGHBORHOOD,
                neighborhoodOrdered(preferredSeed, prioritizedOrders), Math.min(3, properties.getBundle().getMaxSize()), context));
        candidates.addAll(candidateSeries(seed, BundleFamily.HOLD_TO_BATCH,
                holdToBatchOrdered(preferredSeed, prioritizedOrders), Math.min(3, properties.getBundle().getMaxSize()), context));
        if (urgentOrder != null) {
            candidates.addAll(candidateSeries(seed, BundleFamily.LATE_RISK_RESCUE,
                    urgentOrdered(urgentOrder, prioritizedOrders), Math.min(2, properties.getBundle().getMaxSize()), context));
            candidates.add(candidate(seed, BundleFamily.URGENT_SINGLE_FALLBACK, List.of(urgentOrder.orderId()), context));
        }
        candidates.addAll(candidateSeries(seed, BundleFamily.DIVERSITY_EXPLORATION,
                diversityOrdered(preferredSeed, prioritizedOrders), Math.min(3, properties.getBundle().getMaxSize()), context));
        candidates.addAll(connectedPairPortfolio(seed, workingOrders, context));
        return candidates.stream().filter(candidate -> !candidate.orderIds().isEmpty()).toList();
    }

    private List<BundleCandidate> connectedPairPortfolio(BundleSeed seed, List<Order> workingOrders, BundleContext context) {
        if (properties.getBundle().getMinSize() > 2 || workingOrders.size() < 2) {
            return List.of();
        }
        java.util.ArrayList<List<String>> pairs = new java.util.ArrayList<>();
        for (int left = 0; left < workingOrders.size(); left++) {
            for (int right = left + 1; right < workingOrders.size(); right++) {
                String leftOrderId = workingOrders.get(left).orderId();
                String rightOrderId = workingOrders.get(right).orderId();
                if (context.hasSupport(leftOrderId, rightOrderId)) {
                    pairs.add(List.of(leftOrderId, rightOrderId));
                }
            }
        }
        return pairs.stream()
                .sorted(Comparator
                        .comparingDouble((List<String> pair) -> context.support(pair.get(0), pair.get(1))).reversed()
                        .thenComparing(pair -> context.orderSetSignature(pair)))
                .limit(Math.max(4, properties.getBundle().getBeamWidth() * 2L))
                .map(pair -> candidate(seed, BundleFamily.COMPACT_CLIQUE, pair, context))
                .toList();
    }

    private List<BundleCandidate> candidateSeries(BundleSeed seed,
                                                  BundleFamily family,
                                                  List<Order> orderedOrders,
                                                  int maxSize,
                                                  BundleContext context) {
        int lowerBound = Math.max(2, properties.getBundle().getMinSize());
        int upperBound = Math.min(properties.getBundle().getMaxSize(), maxSize);
        if (orderedOrders.size() < lowerBound || upperBound < lowerBound) {
            return List.of();
        }
        java.util.ArrayList<BundleCandidate> candidates = new java.util.ArrayList<>();
        for (int size = lowerBound; size <= upperBound; size++) {
            List<String> orderIds = bundleOrders(orderedOrders.getFirst(), orderedOrders, size);
            if (orderIds.size() == size) {
                candidates.add(candidate(seed, family, orderIds, context));
            }
        }
        return candidates;
    }

    private BundleCandidate candidate(BundleSeed seed, BundleFamily family, List<String> orderIds, BundleContext context) {
        List<String> distinctOrders = orderIds.stream().distinct().sorted().toList();
        String orderSetSignature = context.orderSetSignature(distinctOrders);
        String seedOrderId = distinctOrders.isEmpty() ? "none" : distinctOrders.getFirst();
        String corridorSignature = distinctOrders.isEmpty() ? "unknown" : corridorSignature(context.order(seedOrderId));
        List<String> acceptedBoundaryOrderIds = distinctOrders.stream()
                .filter(seed.acceptedBoundaryOrderIds()::contains)
                .toList();
        return new BundleCandidate(
                "bundle-candidate/v1",
                "%s|%s|%s".formatted(family.name(), orderSetSignature, seedOrderId),
                BundleProposalSource.DETERMINISTIC_FAMILY,
                family,
                seed.cluster().clusterId(),
                family == BundleFamily.BOUNDARY_CROSS,
                acceptedBoundaryOrderIds,
                distinctOrders,
                orderSetSignature,
                seedOrderId,
                corridorSignature,
                0.0,
                false,
                List.of());
    }

    private List<String> bundleOrders(Order seedOrder, List<Order> prioritizedOrders, int maxSize) {
        LinkedHashSet<String> orderIds = new LinkedHashSet<>();
        orderIds.add(seedOrder.orderId());
        for (Order order : prioritizedOrders) {
            if (orderIds.size() >= maxSize) {
                break;
            }
            orderIds.add(order.orderId());
        }
        return List.copyOf(orderIds);
    }

    private List<Order> orderedWithSeedFirst(Order seedOrder, List<Order> prioritizedOrders) {
        LinkedHashSet<Order> orders = new LinkedHashSet<>();
        orders.add(seedOrder);
        orders.addAll(prioritizedOrders);
        return List.copyOf(orders);
    }

    private List<Order> corridorOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> corridorSignature(order))
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> readyOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing(Order::readyAt).thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> boundaryOrdered(Order seedOrder,
                                        List<Order> prioritizedOrders,
                                        List<String> acceptedBoundaryOrderIds,
                                        BundleContext context) {
        LinkedHashSet<String> orderIds = new LinkedHashSet<>();
        orderIds.add(seedOrder.orderId());
        acceptedBoundaryOrderIds.stream().sorted().limit(2).forEach(orderIds::add);
        for (Order order : prioritizedOrders) {
            if (orderIds.size() >= properties.getBundle().getMaxSize()) {
                break;
            }
            orderIds.add(order.orderId());
        }
        return orderIds.stream()
                .map(context::order)
                .filter(java.util.Objects::nonNull)
                .toList();
    }

    private List<Order> urgentOrdered(Order urgentOrder, List<Order> prioritizedOrders) {
        LinkedHashSet<Order> orders = new LinkedHashSet<>();
        orders.add(urgentOrder);
        for (Order order : prioritizedOrders) {
            if (orders.size() >= properties.getBundle().getMaxSize()) {
                break;
            }
            if (!order.urgent()) {
                orders.add(order);
            }
        }
        return List.copyOf(orders);
    }

    private List<Order> landingValueOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> corridorSignature(order)).reversed()
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }


    private List<Order> samePickupOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        String seedCell = pickupCell(seedOrder, 1000.0);
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> pickupCell(order, 1000.0).equals(seedCell) ? 0 : 1)
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> pickupCellOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        String seedCell = pickupCell(seedOrder, 250.0);
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> pickupCell(order, 250.0).equals(seedCell) ? 0 : 1)
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> dropoffCellOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        String seedCell = dropoffCell(seedOrder, 200.0);
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> dropoffCell(order, 200.0).equals(seedCell) ? 0 : 1)
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> neighborhoodOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        String pickup = pickupCell(seedOrder, 200.0);
        String dropoff = dropoffCell(seedOrder, 200.0);
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> (pickupCell(order, 200.0).equals(pickup) || dropoffCell(order, 200.0).equals(dropoff)) ? 0 : 1)
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> holdToBatchOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .filter(order -> !order.urgent())
                .sorted(Comparator.comparing(Order::promisedEtaMinutes).reversed()
                        .thenComparing(Order::readyAt)
                        .thenComparing(Order::orderId))
                .toList());
    }

    private List<Order> diversityOrdered(Order seedOrder, List<Order> prioritizedOrders) {
        return orderedWithSeedFirst(seedOrder, prioritizedOrders.stream()
                .sorted(Comparator.comparing((Order order) -> pickupCell(order, 100.0))
                        .thenComparing(order -> dropoffCell(order, 100.0))
                        .thenComparing(Order::orderId))
                .toList());
    }

    private String pickupCell(Order order, double scale) {
        return "%d:%d".formatted(
                Math.round(order.pickupPoint().latitude() * scale),
                Math.round(order.pickupPoint().longitude() * scale));
    }

    private String dropoffCell(Order order, double scale) {
        return "%d:%d".formatted(
                Math.round(order.dropoffPoint().latitude() * scale),
                Math.round(order.dropoffPoint().longitude() * scale));
    }

    private String corridorSignature(Order order) {
        return "%d:%d".formatted(
                Math.round(order.dropoffPoint().latitude() - order.pickupPoint().latitude()),
                Math.round(order.dropoffPoint().longitude() - order.pickupPoint().longitude()));
    }
}
