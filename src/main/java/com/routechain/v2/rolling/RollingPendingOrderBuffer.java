package com.routechain.v2.rolling;

import com.routechain.domain.Order;
import com.routechain.v2.DispatchV2Request;

import java.time.Instant;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class RollingPendingOrderBuffer {
    private final Map<String, BufferedOrder> bufferedOrders = new ConcurrentHashMap<>();

    public DispatchV2Request mergeDueOrders(DispatchV2Request request) {
        Instant decisionTime = decisionTime(request);
        Map<String, Order> merged = new LinkedHashMap<>();
        request.openOrders().stream()
                .sorted(Comparator.comparing(Order::orderId))
                .forEach(order -> merged.put(order.orderId(), order));
        bufferedOrders.values().stream()
                .filter(buffered -> !buffered.releaseAt().isAfter(decisionTime))
                .sorted(Comparator.comparing(buffered -> buffered.order().orderId()))
                .forEach(buffered -> merged.putIfAbsent(buffered.order().orderId(), buffered.order()));
        return new DispatchV2Request(
                request.schemaVersion(),
                request.traceId(),
                merged.values().stream().toList(),
                request.availableDrivers(),
                request.regions(),
                request.weatherProfile(),
                request.decisionTime());
    }

    public void update(DispatchV2Request request, List<RollingHoldDecision> decisions) {
        Instant decisionTime = decisionTime(request);
        Map<String, Order> orderById = request.openOrders().stream()
                .collect(java.util.stream.Collectors.toMap(Order::orderId, order -> order, (left, right) -> left));
        for (RollingHoldDecision decision : decisions) {
            Order order = orderById.get(decision.orderId());
            if (order == null) {
                continue;
            }
            if (decision.decisionMode() == RollingDecisionMode.HOLD_SHORT && decision.holdSeconds() > 0L) {
                bufferedOrders.put(order.orderId(), new BufferedOrder(order, decisionTime.plusSeconds(decision.holdSeconds()), decision.reasonCodes()));
            } else {
                bufferedOrders.remove(order.orderId());
            }
        }
    }

    public int size() {
        return bufferedOrders.size();
    }

    public List<String> bufferedOrderIds() {
        return bufferedOrders.keySet().stream().sorted().toList();
    }

    private Instant decisionTime(DispatchV2Request request) {
        return request.decisionTime() == null ? Instant.now() : request.decisionTime();
    }

    private record BufferedOrder(Order order, Instant releaseAt, List<String> reasonCodes) {
        private BufferedOrder {
            reasonCodes = reasonCodes == null ? List.of() : List.copyOf(reasonCodes);
        }
    }
}
