package com.routefood.app.data.model;

import java.util.List;

public class Assignment {
    private final String id;
    private final String driverId;
    private final List<String> orderIds;
    private final String status;
    private final int etaMin;
    private final String risk;
    private final String routeSummary;
    private final List<String> routeSteps;
    private final List<RouteStop> routeStops;

    public Assignment(String id, String driverId, List<String> orderIds, String status, int etaMin, String risk) {
        this(id, driverId, orderIds, status, etaMin, risk, "", java.util.Collections.emptyList(), java.util.Collections.emptyList());
    }

    public Assignment(String id, String driverId, List<String> orderIds, String status, int etaMin, String risk, String routeSummary, List<String> routeSteps) {
        this(id, driverId, orderIds, status, etaMin, risk, routeSummary, routeSteps, java.util.Collections.emptyList());
    }

    public Assignment(String id, String driverId, List<String> orderIds, String status, int etaMin, String risk, String routeSummary, List<String> routeSteps, List<RouteStop> routeStops) {
        this.id = id;
        this.driverId = driverId;
        this.orderIds = orderIds;
        this.status = status;
        this.etaMin = etaMin;
        this.risk = risk;
        this.routeSummary = routeSummary;
        this.routeSteps = routeSteps;
        this.routeStops = routeStops;
    }

    public String id() {
        return id;
    }

    public String driverId() {
        return driverId;
    }

    public List<String> orderIds() {
        return orderIds;
    }

    public String status() {
        return status;
    }

    public int etaMin() {
        return etaMin;
    }

    public String risk() {
        return risk;
    }

    public String routeSummary() {
        return routeSummary;
    }

    public List<String> routeSteps() {
        return routeSteps;
    }

    public List<RouteStop> routeStops() {
        return routeStops;
    }
}
