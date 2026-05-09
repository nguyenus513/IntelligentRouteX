package com.routechain.api;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.executor.DispatchAssignment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/api/v1/dispatch")
public final class LiveDispatchController {
    private static final String REQUEST_SCHEMA = "live-dispatch-snapshot/v1";
    private static final String RESPONSE_SCHEMA = "live-dispatch-solver-response/v1";
    private static final String SOLVER_ID = "dispatch-v2-compatible-core";

    private final DispatchV2CompatibleCore dispatchCore;

    public LiveDispatchController(DispatchV2CompatibleCore dispatchCore) {
        this.dispatchCore = dispatchCore;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of(
                "schemaVersion", "dispatch-api-health/v1",
                "status", "ok",
                "endpoint", "/api/v1/dispatch/solve");
    }

    @PostMapping("/solve")
    public ResponseEntity<LiveDispatchSolverResponse> solve(@RequestBody LiveDispatchSnapshotRequest snapshot) {
        long startedAt = System.nanoTime();
        try {
            DispatchV2Request request = toDispatchRequest(snapshot);
            DispatchV2Result result = dispatchCore.dispatch(request);
            long runtimeMs = (System.nanoTime() - startedAt) / 1_000_000L;
            return ResponseEntity.ok(toResponse(snapshot, result, runtimeMs));
        } catch (IllegalArgumentException exception) {
            long runtimeMs = (System.nanoTime() - startedAt) / 1_000_000L;
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorResponse(snapshot, runtimeMs, exception.getMessage()));
        }
    }

    private DispatchV2Request toDispatchRequest(LiveDispatchSnapshotRequest snapshot) {
        if (snapshot == null) {
            throw new IllegalArgumentException("request body is required");
        }
        requireEquals("schemaVersion", REQUEST_SCHEMA, snapshot.schemaVersion());
        requireText("snapshotId", snapshot.snapshotId());
        requireText("timestamp", snapshot.timestamp());
        requireText("region", snapshot.region());
        Instant decisionTime = parseInstant(snapshot.timestamp());
        List<LiveOrder> inputOrders = requireList("orders", snapshot.orders());
        List<LiveDriver> inputDrivers = requireList("drivers", snapshot.drivers());
        List<String> nodeIds = snapshot.nodeIds() == null ? List.of() : snapshot.nodeIds();
        Map<String, LiveGeoPoint> nodeCoordinates = snapshot.nodeCoordinates() == null ? Map.of() : snapshot.nodeCoordinates();
        Map<String, Integer> nodeIndex = nodeIndex(nodeIds);

        List<Order> orders = inputOrders.stream()
                .map(order -> toOrder(order, decisionTime, nodeIndex, nodeCoordinates))
                .toList();
        List<Driver> drivers = inputDrivers.stream()
                .map(driver -> toDriver(driver, nodeIndex, nodeCoordinates))
                .toList();
        Region region = new Region(snapshot.region(), snapshot.region());
        return new DispatchV2Request(
                "dispatch-v2-request/v1",
                snapshot.snapshotId(),
                orders,
                drivers,
                List.of(region),
                weatherProfile(snapshot),
                decisionTime);
    }

    private Order toOrder(LiveOrder input, Instant decisionTime, Map<String, Integer> nodeIndex, Map<String, LiveGeoPoint> nodeCoordinates) {
        if (input == null) {
            throw new IllegalArgumentException("orders must not contain null entries");
        }
        requireText("orders[].orderId", input.orderId());
        requireText("orders[].pickupNodeId", input.pickupNodeId());
        requireText("orders[].dropoffNodeId", input.dropoffNodeId());
        GeoPoint pickup = pointFor(input.pickupNodeId(), input.pickupPoint(), nodeIndex, nodeCoordinates, "orders[].pickupNodeId");
        GeoPoint dropoff = pointFor(input.dropoffNodeId(), input.dropoffPoint(), nodeIndex, nodeCoordinates, "orders[].dropoffNodeId");
        int readyMinutes = nonNegative(input.readyTime(), "orders[].readyTime");
        int dueMinutes = positive(input.dueTime(), "orders[].dueTime");
        boolean urgent = input.priority() != null && input.priority() >= 8;
        return new Order(
                input.orderId(),
                pickup,
                dropoff,
                decisionTime,
                decisionTime.plusSeconds(readyMinutes * 60L),
                dueMinutes,
                urgent);
    }

    private Driver toDriver(LiveDriver input, Map<String, Integer> nodeIndex, Map<String, LiveGeoPoint> nodeCoordinates) {
        if (input == null) {
            throw new IllegalArgumentException("drivers must not contain null entries");
        }
        requireText("drivers[].driverId", input.driverId());
        requireText("drivers[].startNodeId", input.startNodeId());
        GeoPoint start = pointFor(input.startNodeId(), input.currentLocation(), nodeIndex, nodeCoordinates, "drivers[].startNodeId");
        return new Driver(input.driverId(), start);
    }

    private GeoPoint pointFor(String nodeId, LiveGeoPoint explicitPoint, Map<String, Integer> nodeIndex, Map<String, LiveGeoPoint> nodeCoordinates, String field) {
        LiveGeoPoint point = explicitPoint != null ? explicitPoint : nodeCoordinates.get(nodeId);
        if (point != null) {
            return new GeoPoint(point.latitude(), point.longitude());
        }
        Integer index = nodeIndex.get(nodeId);
        if (index == null) {
            throw new IllegalArgumentException(field + " references unknown nodeId: " + nodeId);
        }
        return syntheticPoint(index);
    }

    private GeoPoint syntheticPoint(int index) {
        return new GeoPoint(10.7500 + index * 0.001, 106.6500 + index * 0.001);
    }

    private WeatherProfile weatherProfile(LiveDispatchSnapshotRequest snapshot) {
        if (snapshot.weatherProfile() != null && !snapshot.weatherProfile().isBlank()) {
            try {
                return WeatherProfile.valueOf(snapshot.weatherProfile().trim().toUpperCase());
            } catch (IllegalArgumentException ignored) {
                throw new IllegalArgumentException("weatherProfile must be CLEAR, LIGHT_RAIN, or HEAVY_RAIN");
            }
        }
        Object trafficMode = snapshot.trafficContext() == null ? null : snapshot.trafficContext().get("trafficMode");
        Object scenario = snapshot.trafficContext() == null ? null : snapshot.trafficContext().get("scenario");
        String value = String.valueOf(trafficMode == null ? scenario : trafficMode).toLowerCase();
        if (value.contains("heavy") || value.contains("rain_peak") || value.contains("storm")) {
            return WeatherProfile.HEAVY_RAIN;
        }
        if (value.contains("rain")) {
            return WeatherProfile.LIGHT_RAIN;
        }
        return WeatherProfile.CLEAR;
    }

    private LiveDispatchSolverResponse toResponse(LiveDispatchSnapshotRequest snapshot, DispatchV2Result result, long runtimeMs) {
        List<DispatchAssignment> resultAssignments = result.assignments() == null ? List.of() : result.assignments();
        List<ApiAssignment> assignments = resultAssignments.stream().map(this::apiAssignment).toList();
        List<ApiRouteSequence> routeSequences = resultAssignments.stream().map(this::apiRouteSequence).toList();
        Set<String> accepted = new LinkedHashSet<>();
        for (DispatchAssignment assignment : resultAssignments) {
            accepted.addAll(assignment.orderIds());
        }
        List<ApiRejectedOrder> rejected = rejectedOrders(snapshot.orders(), accepted, result.fallbackUsed());
        Map<String, Object> diagnostics = diagnostics(snapshot, result, runtimeMs);
        return new LiveDispatchSolverResponse(
                RESPONSE_SCHEMA,
                snapshot.snapshotId(),
                SOLVER_ID,
                mode(snapshot),
                assignments,
                routeSequences,
                List.copyOf(accepted),
                rejected,
                result.fallbackUsed() ? "dispatch-v2-fallback-output" : null,
                runtimeMs,
                List.of(),
                diagnostics);
    }

    private LiveDispatchSolverResponse errorResponse(LiveDispatchSnapshotRequest snapshot, long runtimeMs, String message) {
        String snapshotId = snapshot == null || snapshot.snapshotId() == null ? "unknown" : snapshot.snapshotId();
        return new LiveDispatchSolverResponse(
                RESPONSE_SCHEMA,
                snapshotId,
                SOLVER_ID,
                snapshot == null ? "shadow" : mode(snapshot),
                List.of(),
                List.of(),
                List.of(),
                List.of(),
                "invalid-request",
                runtimeMs,
                List.of(new ApiViolation("request-validation", message == null ? "invalid request" : message, "hard")),
                Map.of("accepted", false));
    }

    private ApiAssignment apiAssignment(DispatchAssignment assignment) {
        return new ApiAssignment(
                assignment.assignmentId(),
                assignment.driverId(),
                assignment.orderIds(),
                assignment.projectedPickupEtaMinutes(),
                assignment.projectedCompletionEtaMinutes(),
                assignment.selectionRank(),
                assignment.selectionScore(),
                assignment.robustUtility(),
                assignment.reasons(),
                assignment.degradeReasons());
    }

    private ApiRouteSequence apiRouteSequence(DispatchAssignment assignment) {
        return new ApiRouteSequence(
                assignment.driverId(),
                assignment.assignmentId(),
                assignment.stopOrder(),
                assignment.projectedCompletionEtaMinutes(),
                assignment.routeSource() == null ? "unknown" : assignment.routeSource().name());
    }

    private List<ApiRejectedOrder> rejectedOrders(List<LiveOrder> orders, Set<String> accepted, boolean fallbackUsed) {
        if (orders == null) {
            return List.of();
        }
        List<ApiRejectedOrder> rejected = new ArrayList<>();
        for (LiveOrder order : orders) {
            if (order != null && !accepted.contains(order.orderId())) {
                rejected.add(new ApiRejectedOrder(order.orderId(), fallbackUsed ? "fallback-output" : "not-selected-by-global-selector"));
            }
        }
        return rejected;
    }

    private Map<String, Object> diagnostics(LiveDispatchSnapshotRequest snapshot, DispatchV2Result result, long runtimeMs) {
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("traceId", result.traceId());
        diagnostics.put("inputSchemaVersion", snapshot.schemaVersion());
        diagnostics.put("orderCount", snapshot.orders() == null ? 0 : snapshot.orders().size());
        diagnostics.put("driverCount", snapshot.drivers() == null ? 0 : snapshot.drivers().size());
        diagnostics.put("activeRouteCount", snapshot.activeRoutes() == null ? 0 : snapshot.activeRoutes().size());
        diagnostics.put("durationMatrixSize", snapshot.durationMatrix() == null ? 0 : snapshot.durationMatrix().size());
        diagnostics.put("decisionStages", result.decisionStages() == null ? List.of() : result.decisionStages());
        diagnostics.put("stageLatencies", result.stageLatencies() == null ? List.of() : result.stageLatencies());
        diagnostics.put("latencyBudgetSummary", result.latencyBudgetSummary());
        diagnostics.put("globalSelectorSummary", result.globalSelectorSummary());
        diagnostics.put("dispatchExecutionSummary", result.dispatchExecutionSummary());
        diagnostics.put("fallbackUsed", result.fallbackUsed());
        diagnostics.put("degradeReasons", result.degradeReasons() == null ? List.of() : result.degradeReasons());
        diagnostics.put("runtimeMs", runtimeMs);
        return diagnostics;
    }

    private String mode(LiveDispatchSnapshotRequest snapshot) {
        return snapshot.mode() == null || snapshot.mode().isBlank() ? "shadow" : snapshot.mode();
    }

    private Map<String, Integer> nodeIndex(List<String> nodeIds) {
        Map<String, Integer> index = new LinkedHashMap<>();
        for (int i = 0; i < nodeIds.size(); i++) {
            index.put(nodeIds.get(i), i);
        }
        return index;
    }

    private Instant parseInstant(String value) {
        try {
            return Instant.parse(value);
        } catch (DateTimeParseException ignored) {
            try {
                return java.time.OffsetDateTime.parse(value).toInstant();
            } catch (DateTimeParseException exception) {
                throw new IllegalArgumentException("timestamp must be ISO-8601 instant or offset datetime");
            }
        }
    }

    private void requireEquals(String field, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new IllegalArgumentException(field + " must be " + expected);
        }
    }

    private void requireText(String field, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
    }

    private <T> List<T> requireList(String field, List<T> value) {
        if (value == null) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value;
    }

    private int nonNegative(Integer value, String field) {
        if (value == null || value < 0) {
            throw new IllegalArgumentException(field + " must be >= 0");
        }
        return value;
    }

    private int positive(Integer value, String field) {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(field + " must be > 0");
        }
        return value;
    }

    public record LiveDispatchSnapshotRequest(
            String schemaVersion,
            String snapshotId,
            String timestamp,
            String region,
            String mode,
            String weatherProfile,
            List<String> nodeIds,
            Map<String, LiveGeoPoint> nodeCoordinates,
            List<LiveOrder> orders,
            List<LiveDriver> drivers,
            List<Map<String, Object>> activeRoutes,
            List<List<Double>> durationMatrix,
            Map<String, Object> trafficContext,
            Map<String, Object> restaurantDelay,
            Map<String, Object> cancellationRisk) {
    }

    public record LiveOrder(
            String orderId,
            String pickupNodeId,
            String dropoffNodeId,
            String restaurantId,
            Integer readyTime,
            Integer dueTime,
            Integer serviceTimePickup,
            Integer serviceTimeDropoff,
            Integer demand,
            Integer priority,
            LiveGeoPoint pickupPoint,
            LiveGeoPoint dropoffPoint) {
    }

    public record LiveDriver(
            String driverId,
            String startNodeId,
            Integer capacity,
            Integer shiftStart,
            Integer shiftEnd,
            List<String> skills,
            Integer currentLoad,
            Integer maxTasks,
            String endNodeId,
            Boolean openRouteAllowed,
            LiveGeoPoint currentLocation) {
    }

    public record LiveGeoPoint(double latitude, double longitude) {
    }

    public record LiveDispatchSolverResponse(
            String schemaVersion,
            String snapshotId,
            String solver,
            String mode,
            List<ApiAssignment> assignments,
            List<ApiRouteSequence> routeSequences,
            List<String> acceptedOrders,
            List<ApiRejectedOrder> rejectedOrders,
            String fallbackReason,
            long runtimeMs,
            List<ApiViolation> violations,
            Map<String, Object> diagnostics) {
    }

    public record ApiAssignment(
            String assignmentId,
            String driverId,
            List<String> orderIds,
            double pickupEtaMinutes,
            double dropoffEtaMinutes,
            int selectionRank,
            double selectionScore,
            double robustUtility,
            List<String> reasons,
            List<String> degradeReasons) {
    }

    public record ApiRouteSequence(
            String driverId,
            String assignmentId,
            List<String> stops,
            double projectedCompletionEtaMinutes,
            String routeSource) {
    }

    public record ApiRejectedOrder(String orderId, String reason) {
    }

    public record ApiViolation(String type, String message, String severity) {
    }
}
