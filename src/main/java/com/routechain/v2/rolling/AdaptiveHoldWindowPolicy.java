package com.routechain.v2.rolling;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class AdaptiveHoldWindowPolicy {
    private static final double NEARBY_ORDER_RADIUS = 0.020;
    private static final double NEARBY_DRIVER_RADIUS = 0.035;
    private static final long URGENT_PROMISE_SLACK_SECONDS = 12 * 60L;
    private static final long LOW_PROMISE_SLACK_SECONDS = 18 * 60L;
    private static final long MAX_HOLD_SECONDS = 180L;

    public List<RollingHoldDecision> decide(RollingDispatchState state) {
        List<RollingOrderState> orderStates = orderStates(state);
        return orderStates.stream()
                .map(orderState -> decideOrder(orderState, state.weatherProfile()))
                .toList();
    }

    public List<RollingOrderState> orderStates(RollingDispatchState state) {
        return state.pendingOrders().stream()
                .sorted(Comparator.comparing(Order::orderId))
                .map(order -> orderState(order, state))
                .toList();
    }

    private RollingOrderState orderState(Order order, RollingDispatchState state) {
        long orderAge = Math.max(0L, Duration.between(order.createdAt(), state.decisionTime()).toSeconds());
        long readySlack = Duration.between(state.decisionTime(), order.readyAt()).toSeconds();
        long promiseSlack = Duration.between(state.decisionTime(), order.createdAt().plusSeconds(order.promisedEtaMinutes() * 60L)).toSeconds();
        double density = nearbyOrderDensity(order, state.pendingOrders());
        double nearestDriverScore = nearestDriverScore(order, state.availableDrivers());
        double readyCompatibility = readyCompatibility(order, state.pendingOrders());
        double corridorCompatibility = corridorCompatibility(order, state.pendingOrders());
        double bundleOpportunity = clamp(0.35 * density + 0.25 * readyCompatibility + 0.25 * corridorCompatibility + 0.15 * nearestDriverScore);
        List<String> reasons = new ArrayList<>();
        if (density >= 0.55) {
            reasons.add("dense-nearby-orders");
        }
        if (readyCompatibility >= 0.65) {
            reasons.add("ready-compatible-neighbors");
        }
        if (corridorCompatibility >= 0.65) {
            reasons.add("corridor-compatible-neighbors");
        }
        if (nearestDriverScore < 0.35) {
            reasons.add("low-driver-proximity");
        }
        if (order.urgent()) {
            reasons.add("urgent-order");
        }
        return new RollingOrderState(
                "rolling-order-state/v1",
                order.orderId(),
                orderAge,
                readySlack,
                promiseSlack,
                density,
                bundleOpportunity,
                nearestDriverScore,
                order.urgent(),
                readySlack <= 0L,
                reasons);
    }

    private RollingHoldDecision decideOrder(RollingOrderState orderState, WeatherProfile weatherProfile) {
        List<String> reasons = new ArrayList<>(orderState.reasonCodes());
        double weatherRisk = weatherRisk(weatherProfile);
        double urgencyRisk = urgencyRisk(orderState);
        double riskScore = clamp(0.55 * urgencyRisk + 0.25 * weatherRisk + 0.20 * Math.max(0.0, 1.0 - orderState.nearestDriverScore()));
        if (orderState.urgent() || orderState.promiseSlackSeconds() <= URGENT_PROMISE_SLACK_SECONDS) {
            reasons.add("dispatch-now-urgent-or-low-promise-slack");
            return decision(orderState, RollingDecisionMode.DISPATCH_NOW, 0L, 0.96, riskScore, reasons);
        }
        if (weatherRisk >= 0.75 && orderState.bundleOpportunityScore() < 0.80) {
            reasons.add("dispatch-now-weather-risk");
            return decision(orderState, RollingDecisionMode.DISPATCH_NOW, 0L, 0.88, riskScore, reasons);
        }
        if (orderState.bundleOpportunityScore() >= 0.74 && orderState.promiseSlackSeconds() > 30 * 60L) {
            long holdSeconds = weatherRisk >= 0.45 ? 60L : 120L;
            reasons.add("micro-batch-high-opportunity");
            return decision(orderState, RollingDecisionMode.MICRO_BATCH, holdSeconds, 0.86, riskScore, reasons);
        }
        if (orderState.bundleOpportunityScore() >= 0.52 && orderState.promiseSlackSeconds() > LOW_PROMISE_SLACK_SECONDS) {
            long holdSeconds = Math.min(MAX_HOLD_SECONDS, Math.max(30L, Math.round(orderState.bundleOpportunityScore() * 90.0)));
            if (weatherRisk >= 0.45) {
                holdSeconds = Math.min(holdSeconds, 45L);
            }
            reasons.add("hold-short-medium-opportunity");
            return decision(orderState, RollingDecisionMode.HOLD_SHORT, holdSeconds, 0.78, riskScore, reasons);
        }
        if (!orderState.ready() && orderState.readySlackSeconds() > 0L && orderState.readySlackSeconds() <= 8 * 60L && orderState.promiseSlackSeconds() > LOW_PROMISE_SLACK_SECONDS) {
            long holdSeconds = Math.min(60L, Math.max(15L, orderState.readySlackSeconds() / 2L));
            reasons.add("hold-short-wait-for-ready");
            return decision(orderState, RollingDecisionMode.HOLD_SHORT, holdSeconds, 0.72, riskScore, reasons);
        }
        if (orderState.nearestDriverScore() < 0.30 && orderState.bundleOpportunityScore() >= 0.45 && orderState.promiseSlackSeconds() > LOW_PROMISE_SLACK_SECONDS) {
            reasons.add("reoptimize-active-route-low-driver-proximity");
            return decision(orderState, RollingDecisionMode.REOPTIMIZE_ACTIVE_ROUTE, 30L, 0.70, riskScore, reasons);
        }
        reasons.add("dispatch-now-sparse-or-low-opportunity");
        return decision(orderState, RollingDecisionMode.DISPATCH_NOW, 0L, 0.82, riskScore, reasons);
    }

    private RollingHoldDecision decision(RollingOrderState orderState,
                                         RollingDecisionMode mode,
                                         long holdSeconds,
                                         double confidence,
                                         double riskScore,
                                         List<String> reasons) {
        long guardedHold = Math.min(holdSeconds, Math.max(0L, orderState.promiseSlackSeconds() - URGENT_PROMISE_SLACK_SECONDS));
        return new RollingHoldDecision(
                "rolling-hold-decision/v1",
                orderState.orderId(),
                guardedHold <= 0L && mode != RollingDecisionMode.DISPATCH_NOW ? RollingDecisionMode.DISPATCH_NOW : mode,
                Math.max(0L, guardedHold),
                clamp(confidence),
                orderState.bundleOpportunityScore(),
                riskScore,
                List.copyOf(reasons));
    }

    private double nearbyOrderDensity(Order order, List<Order> orders) {
        if (orders.size() <= 1) {
            return 0.0;
        }
        long nearby = orders.stream()
                .filter(candidate -> !candidate.orderId().equals(order.orderId()))
                .filter(candidate -> distance(order.pickupPoint(), candidate.pickupPoint()) <= NEARBY_ORDER_RADIUS)
                .count();
        return clamp((double) nearby / Math.max(1.0, Math.min(5.0, orders.size() - 1.0)));
    }

    private double nearestDriverScore(Order order, List<Driver> drivers) {
        if (drivers.isEmpty()) {
            return 0.0;
        }
        double nearest = drivers.stream()
                .mapToDouble(driver -> distance(driver.currentLocation(), order.pickupPoint()))
                .min()
                .orElse(NEARBY_DRIVER_RADIUS);
        return clamp(1.0 - nearest / NEARBY_DRIVER_RADIUS);
    }

    private double readyCompatibility(Order order, List<Order> orders) {
        if (orders.size() <= 1) {
            return 0.0;
        }
        return orders.stream()
                .filter(candidate -> !candidate.orderId().equals(order.orderId()))
                .mapToDouble(candidate -> {
                    double gapMinutes = Math.abs(Duration.between(order.readyAt(), candidate.readyAt()).toMinutes());
                    return clamp(1.0 - gapMinutes / 12.0);
                })
                .max()
                .orElse(0.0);
    }

    private double corridorCompatibility(Order order, List<Order> orders) {
        if (orders.size() <= 1) {
            return 0.0;
        }
        double bearing = bearing(order);
        return orders.stream()
                .filter(candidate -> !candidate.orderId().equals(order.orderId()))
                .mapToDouble(candidate -> clamp(1.0 - bearingDelta(bearing, bearing(candidate)) / 120.0))
                .max()
                .orElse(0.0);
    }

    private double urgencyRisk(RollingOrderState orderState) {
        if (orderState.urgent()) {
            return 1.0;
        }
        return clamp(1.0 - orderState.promiseSlackSeconds() / (30.0 * 60.0));
    }

    private double weatherRisk(WeatherProfile weatherProfile) {
        if (weatherProfile == WeatherProfile.HEAVY_RAIN) {
            return 0.85;
        }
        if (weatherProfile == WeatherProfile.LIGHT_RAIN) {
            return 0.45;
        }
        return 0.0;
    }

    private double bearing(Order order) {
        double y = order.dropoffPoint().longitude() - order.pickupPoint().longitude();
        double x = order.dropoffPoint().latitude() - order.pickupPoint().latitude();
        return Math.toDegrees(Math.atan2(y, x));
    }

    private double bearingDelta(double left, double right) {
        double delta = Math.abs(left - right) % 360.0;
        return delta > 180.0 ? 360.0 - delta : delta;
    }

    private double distance(GeoPoint left, GeoPoint right) {
        double latitude = left.latitude() - right.latitude();
        double longitude = left.longitude() - right.longitude();
        return Math.sqrt((latitude * latitude) + (longitude * longitude));
    }

    private double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }
}
