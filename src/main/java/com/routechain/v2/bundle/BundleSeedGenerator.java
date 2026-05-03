package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.v2.cluster.MicroCluster;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class BundleSeedGenerator {
    private final RouteChainDispatchV2Properties properties;

    public BundleSeedGenerator(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public List<BundleSeed> generate(List<MicroCluster> microClusters, BundleContext context) {
        List<BundleSeed> seeds = new ArrayList<>();
        for (MicroCluster cluster : microClusters.stream().sorted(Comparator.comparing(MicroCluster::clusterId)).toList()) {
            BoundaryExpansion expansion = context.expansionFor(cluster);
            List<String> acceptedBoundaryOrderIds = expansion == null ? List.of() : expansion.acceptedBoundaryOrderIds();
            List<String> distinctWorkingOrders = java.util.stream.Stream.concat(
                            cluster.orderIds().stream(),
                            acceptedBoundaryOrderIds.stream())
                    .distinct()
                    .sorted()
                    .toList();
            List<String> prioritizedOrderIds = distinctWorkingOrders.stream()
                    .sorted(Comparator
                            .comparingDouble((String orderId) -> expansion == null ? 0.0 : expansion.supportScoreByOrder().getOrDefault(orderId, 0.0))
                            .reversed()
                            .thenComparing(orderId -> context.order(orderId).readyAt())
                            .thenComparing(orderId -> orderId))
                    .limit(properties.getBundle().getTopNeighbors())
                    .toList();
            seeds.add(new BundleSeed(
                    cluster,
                    distinctWorkingOrders,
                    acceptedBoundaryOrderIds,
                    prioritizedOrderIds,
                    expansion == null ? java.util.Map.of() : expansion.supportScoreByOrder()));
        }
        supplementalDenseSeed(microClusters, context, seeds).ifPresent(seeds::add);
        return List.copyOf(seeds);
    }

    private java.util.Optional<BundleSeed> supplementalDenseSeed(List<MicroCluster> microClusters,
                                                                BundleContext context,
                                                                List<BundleSeed> seeds) {
        int minSize = properties.getBundle().getMinSize();
        boolean weakSingletonPool = !seeds.isEmpty()
                && seeds.stream().noneMatch(seed -> seed.workingOrderIds().size() >= minSize);
        List<String> mergedOrderIds = microClusters.stream()
                .flatMap(cluster -> cluster.orderIds().stream())
                .distinct()
                .sorted()
                .limit(properties.getBundle().getTopNeighbors())
                .toList();
        if (!weakSingletonPool || mergedOrderIds.size() < minSize) {
            return java.util.Optional.empty();
        }
        List<Order> orders = mergedOrderIds.stream()
                .map(context::order)
                .filter(java.util.Objects::nonNull)
                .toList();
        if (orders.size() < minSize) {
            return java.util.Optional.empty();
        }
        MicroCluster syntheticCluster = new MicroCluster(
                "micro-cluster/v1",
                "cluster-greedrl-dense-merge",
                mergedOrderIds,
                mergedOrderIds,
                List.of(),
                pickupCentroid(orders),
                orders.stream().mapToDouble(this::dropBearing).average().orElse(0.0),
                corridorSignature(orders),
                timeSpanMinutes(orders));
        List<String> prioritizedOrderIds = closestPairFirst(orders, mergedOrderIds);
        return java.util.Optional.of(new BundleSeed(
                syntheticCluster,
                mergedOrderIds,
                List.of(),
                prioritizedOrderIds,
                java.util.Map.of()));
    }

    private List<String> closestPairFirst(List<Order> orders, List<String> fallbackOrderIds) {
        if (orders.size() < 2) {
            return fallbackOrderIds;
        }
        Order bestLeft = orders.get(0);
        Order bestRight = orders.get(1);
        double bestDistance = Double.POSITIVE_INFINITY;
        for (int i = 0; i < orders.size(); i++) {
            for (int j = i + 1; j < orders.size(); j++) {
                double distance = distanceKm(orders.get(i).pickupPoint(), orders.get(j).pickupPoint());
                if (distance < bestDistance) {
                    bestDistance = distance;
                    bestLeft = orders.get(i);
                    bestRight = orders.get(j);
                }
            }
        }
        List<String> prioritized = new ArrayList<>();
        prioritized.add(bestLeft.orderId());
        prioritized.add(bestLeft.orderId());
        prioritized.add(bestRight.orderId());
        fallbackOrderIds.stream()
                .filter(orderId -> !prioritized.contains(orderId))
                .forEach(prioritized::add);
        return List.copyOf(prioritized);
    }

    private GeoPoint pickupCentroid(List<Order> orders) {
        double avgLat = orders.stream().mapToDouble(order -> order.pickupPoint().latitude()).average().orElse(0.0);
        double avgLon = orders.stream().mapToDouble(order -> order.pickupPoint().longitude()).average().orElse(0.0);
        return new GeoPoint(avgLat, avgLon);
    }

    private String corridorSignature(List<Order> orders) {
        long lat = Math.round(orders.stream().mapToDouble(order -> order.dropoffPoint().latitude() - order.pickupPoint().latitude()).average().orElse(0.0));
        long lon = Math.round(orders.stream().mapToDouble(order -> order.dropoffPoint().longitude() - order.pickupPoint().longitude()).average().orElse(0.0));
        return "%d:%d".formatted(lat, lon);
    }

    private long timeSpanMinutes(List<Order> orders) {
        return orders.stream().map(Order::readyAt).min(java.util.Comparator.naturalOrder())
                .map(min -> orders.stream().map(Order::readyAt).max(java.util.Comparator.naturalOrder())
                        .map(max -> java.time.Duration.between(min, max).toMinutes())
                        .orElse(0L))
                .orElse(0L);
    }

    private double dropBearing(Order order) {
        double y = order.dropoffPoint().longitude() - order.pickupPoint().longitude();
        double x = order.dropoffPoint().latitude() - order.pickupPoint().latitude();
        double degrees = Math.toDegrees(Math.atan2(y, x));
        return degrees < 0 ? degrees + 360.0 : degrees;
    }

    private double distanceKm(GeoPoint left, GeoPoint right) {
        double latKm = (left.latitude() - right.latitude()) * 111.0;
        double lonKm = (left.longitude() - right.longitude()) * 111.0
                * Math.cos(Math.toRadians((left.latitude() + right.latitude()) / 2.0));
        return Math.sqrt(latKm * latKm + lonKm * lonKm);
    }
}
