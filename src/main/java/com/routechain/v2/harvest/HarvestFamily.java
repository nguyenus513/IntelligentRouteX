package com.routechain.v2.harvest;

public enum HarvestFamily {
    HARVEST_RUN_MANIFEST("harvest-run-manifest"),
    DECISION_STAGE_INPUT("decision-stage-input"),
    DECISION_STAGE_OUTPUT("decision-stage-output"),
    DECISION_STAGE_JOIN("decision-stage-join"),
    DISPATCH_EXECUTION("dispatch-execution"),
    DISPATCH_OUTCOME("dispatch-outcome"),
    GEO_TILE_SELECTION_TRACE("geo-tile-selection-trace"),
    TILE_FEATURE_TRACE("tile-feature-trace"),
    BUNDLE_GEOMETRY_TRACE("bundle-geometry-trace"),
    DRIVER_PICKUP_FIT_TRACE("driver-pickup-fit-trace"),
    ROUTE_VECTOR_TRACE("route-vector-trace"),
    ROUTE_STOP_TRACE("route-stop-trace"),
    TRAFFIC_CONTEXT_TRACE("traffic-context-trace"),
    TABULAR_TEACHER_TRACE("tabular-teacher-trace"),
    GREEDRL_TEACHER_TRACE("greedrl-teacher-trace"),
    ROUTEFINDER_TEACHER_TRACE("routefinder-teacher-trace"),
    FORECAST_TEACHER_TRACE("forecast-teacher-trace");

    private final String directoryName;

    HarvestFamily(String directoryName) {
        this.directoryName = directoryName;
    }

    public String directoryName() {
        return directoryName;
    }
}
