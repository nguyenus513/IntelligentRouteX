package com.routechain.v2.bundle;

import com.routechain.domain.Order;
import com.routechain.v2.cluster.MicroCluster;
import com.routechain.v2.cluster.PairEdge;
import com.routechain.v2.cluster.PairSimilarityGraph;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

final class BundleContext {
    private final Map<String, Order> orderById;
    private final Map<String, Map<String, Double>> support;
    private final Map<String, BoundaryExpansion> expansionsByClusterId;

    BundleContext(List<Order> orders, PairSimilarityGraph graph, List<BoundaryExpansion> expansions) {
        this.orderById = orders.stream().collect(java.util.stream.Collectors.toMap(Order::orderId, order -> order));
        this.support = new HashMap<>();
        for (PairEdge edge : graph.edges()) {
            support.computeIfAbsent(edge.leftOrderId(), ignored -> new HashMap<>()).put(edge.rightOrderId(), edge.weight());
            support.computeIfAbsent(edge.rightOrderId(), ignored -> new HashMap<>()).put(edge.leftOrderId(), edge.weight());
        }
        this.expansionsByClusterId = expansions.stream().collect(java.util.stream.Collectors.toMap(BoundaryExpansion::clusterId, expansion -> expansion));
    }

    Order order(String orderId) {
        return orderById.get(orderId);
    }

    List<Order> orders(List<String> orderIds) {
        return orderIds.stream()
                .map(orderById::get)
                .filter(java.util.Objects::nonNull)
                .sorted(Comparator.comparing(Order::orderId))
                .toList();
    }

    List<Order> allOrders() {
        return orderById.values().stream()
                .sorted(Comparator.comparing(Order::orderId))
                .toList();
    }

    double support(String leftOrderId, String rightOrderId) {
        return support.getOrDefault(leftOrderId, Map.of()).getOrDefault(rightOrderId, 0.0);
    }

    boolean hasSupport(String leftOrderId, String rightOrderId) {
        return support(leftOrderId, rightOrderId) > 0.0;
    }

    boolean hasConnectedSupport(List<String> orderIds) {
        if (orderIds.size() <= 1) {
            return true;
        }
        List<String> sorted = orderIds.stream().sorted().toList();
        java.util.ArrayDeque<String> queue = new java.util.ArrayDeque<>();
        java.util.Set<String> visited = new java.util.HashSet<>();
        queue.add(sorted.getFirst());
        visited.add(sorted.getFirst());
        while (!queue.isEmpty()) {
            String current = queue.removeFirst();
            for (String candidate : sorted) {
                if (!visited.contains(candidate) && hasSupport(current, candidate)) {
                    visited.add(candidate);
                    queue.add(candidate);
                }
            }
        }
        return visited.size() == sorted.size();
    }

    String orderSetSignature(List<String> orderIds) {
        return orderIds.stream().sorted().distinct().collect(java.util.stream.Collectors.joining("|"));
    }

    BoundaryExpansion expansionFor(MicroCluster cluster) {
        return expansionsByClusterId.get(cluster.clusterId());
    }

    Map<String, BoundaryExpansion> expansionsByClusterId() {
        return Map.copyOf(expansionsByClusterId);
    }

    double averagePairSupport(List<String> orderIds) {
        if (orderIds.size() <= 1) {
            return 0.0;
        }
        double total = 0.0;
        int count = 0;
        List<String> sorted = orderIds.stream().sorted().toList();
        for (int i = 0; i < sorted.size(); i++) {
            for (int j = i + 1; j < sorted.size(); j++) {
                double weight = support(sorted.get(i), sorted.get(j));
                if (weight > 0.0) {
                    total += weight;
                    count++;
                }
            }
        }
        return count == 0 ? 0.0 : total / count;
    }
}
