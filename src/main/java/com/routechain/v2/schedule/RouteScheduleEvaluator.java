package com.routechain.v2.schedule;

import com.routechain.domain.Order;
import com.routechain.v2.hybrid.BoundRoute;
import com.routechain.v2.hybrid.BoundStop;
import com.routechain.v2.hybrid.DistanceCostFunction;
import com.routechain.v2.hybrid.StopType;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class RouteScheduleEvaluator {
    public RouteSchedule evaluate(BoundRoute route,
                                  List<BoundStop> pathWithoutDriverStart,
                                  DistanceCostFunction distanceCost,
                                  Map<String, Order> orderById,
                                  SchedulePolicy policy,
                                  String legPrefix) {
        SchedulePolicy safePolicy = policy == null ? SchedulePolicy.defaults() : policy;
        if (route == null || distanceCost == null) {
            return empty(route == null ? "unknown" : route.routeId());
        }
        BoundStop start = route.stops().stream()
                .filter(stop -> stop.type() == StopType.DRIVER_START)
                .findFirst()
                .orElse(null);
        if (start == null) {
            return empty(route.routeId());
        }
        List<BoundStop> stops = pathWithoutDriverStart == null
                ? route.stops().stream().filter(stop -> stop.type() != StopType.DRIVER_START).toList()
                : pathWithoutDriverStart;
        Map<String, Order> orders = orderById == null ? Map.of() : orderById;
        List<StopSchedule> stopSchedules = new ArrayList<>();
        Map<String, Double> etaByStop = new LinkedHashMap<>();
        Map<String, Double> deliveryEtaByOrder = new LinkedHashMap<>();
        Map<String, Double> slackByOrder = new LinkedHashMap<>();
        Map<String, OrderSchedule> orderSchedules = new LinkedHashMap<>();
        List<ScheduleViolation> violations = new ArrayList<>();
        double totalKm = 0.0;
        double elapsedMinutes = 0.0;
        BoundStop previous = start;
        for (BoundStop stop : stops) {
            double legKm = distanceCost.distanceKm(
                    legPrefix + "-" + route.routeId() + "-" + previous.stopId() + "-" + stop.stopId(),
                    previous.location().latitude(),
                    previous.location().longitude(),
                    stop.location().latitude(),
                    stop.location().longitude());
            totalKm += legKm;
            elapsedMinutes += legKm / safePolicy.speedKmh() * 60.0;
            double eta = elapsedMinutes;
            double serviceMinutes = stop.type() == StopType.PICKUP ? safePolicy.pickupServiceMinutes()
                    : stop.type() == StopType.DROPOFF ? safePolicy.dropoffServiceMinutes() : 0.0;
            elapsedMinutes += serviceMinutes;
            stopSchedules.add(new StopSchedule(stop.stopId(), stop.orderId(), stop.type(), round(eta), round(elapsedMinutes), round(legKm)));
            etaByStop.put(stop.stopId(), round(eta));
            if (stop.type() == StopType.DROPOFF) {
                Order order = orders.get(stop.orderId());
                double due = order == null ? Double.POSITIVE_INFINITY : order.promisedEtaMinutes();
                double slack = due - eta;
                double lateness = Math.max(0.0, eta - due);
                deliveryEtaByOrder.put(stop.orderId(), round(eta));
                slackByOrder.put(stop.orderId(), round(slack));
                orderSchedules.put(stop.orderId(), new OrderSchedule(stop.orderId(), round(eta), round(due), round(slack), round(lateness), lateness > 0.0));
                if (lateness > 0.0) {
                    violations.add(new ScheduleViolation(route.routeId(), stop.orderId(), "LATE_DROPOFF", round(lateness), "dropoff-after-due-time"));
                }
            }
            previous = stop;
        }
        double totalLateness = orderSchedules.values().stream().mapToDouble(OrderSchedule::latenessMinutes).sum();
        long lateCount = orderSchedules.values().stream().filter(OrderSchedule::late).count();
        return new RouteSchedule(
                route.routeId(),
                round(totalKm),
                round(elapsedMinutes),
                lateCount,
                round(totalLateness),
                stopSchedules,
                etaByStop,
                deliveryEtaByOrder,
                slackByOrder,
                orderSchedules,
                violations);
    }

    private RouteSchedule empty(String routeId) {
        return new RouteSchedule(routeId, 0.0, 0.0, 0, 0.0, List.of(), Map.of(), Map.of(), Map.of(), Map.of(), List.of());
    }

    private double round(double value) {
        if (!Double.isFinite(value)) {
            return value;
        }
        return Math.round(value * 10.0) / 10.0;
    }
}
