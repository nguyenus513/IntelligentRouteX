package com.routechain.v2.external;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.v2.hybrid.CandidateSource;
import com.routechain.v2.hybrid.DriverSeedLoad;
import com.routechain.v2.hybrid.HybridCostBreakdown;
import com.routechain.v2.hybrid.SolutionSeedCandidate;
import com.routechain.v2.hybrid.SolutionSeedRoute;
import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.routing.MatrixCostAdapter;
import com.routechain.v2.unified.UnifiedDispatchRequest;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

public final class PyvrpSeedContributor implements ExternalSeedContributor {
    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().findAndAddModules().build();

    @Override
    public String contributorId() {
        return "PYVRP";
    }

    @Override
    public ExternalSeedContribution contribute(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot) {
        long started = System.nanoTime();
        if (request == null || request.orders().isEmpty() || request.drivers().isEmpty() || matrixSnapshot == null) {
            return skipped("missing-request-or-matrix", started, Map.of("expectedSource", "PYVRP_SEED"));
        }
        try {
            Path root = Path.of("artifacts", "external-seeds", "pyvrp");
            Files.createDirectories(root);
            String trace = request.traceId() == null || request.traceId().isBlank() ? "run" : request.traceId().replaceAll("[^A-Za-z0-9_-]", "_");
            Path input = root.resolve(trace + "-input.json");
            Path output = root.resolve(trace + "-output.json");
            OBJECT_MAPPER.writeValue(input.toFile(), instance(request, matrixSnapshot));
            Process process = new ProcessBuilder("py", "-3", "scripts/run_pyvrp_seed.py",
                    "--input", input.toString(),
                    "--output", output.toString(),
                    "--time-limit-ms", "650")
                    .redirectErrorStream(true)
                    .start();
            boolean completed = process.waitFor(15, TimeUnit.SECONDS);
            String processOutput = new String(process.getInputStream().readAllBytes());
            if (!completed) {
                process.destroyForcibly();
                return skipped("pyvrp-seed-timeout", started, Map.of("input", input.toString(), "output", output.toString()));
            }
            if (process.exitValue() != 0 || !Files.exists(output)) {
                return skipped("pyvrp-seed-runner-failed", started, Map.of("input", input.toString(), "processOutput", processOutput, "exitCode", process.exitValue()));
            }
            JsonNode result = OBJECT_MAPPER.readTree(output.toFile());
            if (!result.path("routes").isArray() || result.path("routes").isEmpty()) {
                return skipped(result.path("evidenceGapReason").asText("pyvrp-no-routes"), started, Map.of("input", input.toString(), "output", output.toString(), "status", result.path("status").asText("")));
            }
            SolutionSeedCandidate seed = seedFromResult(request, matrixSnapshot, result);
            if (seed.routes().isEmpty()) {
                return skipped("pyvrp-seed-empty-after-pd-filter", started, Map.of("input", input.toString(), "output", output.toString()));
            }
            Map<String, Object> diagnostics = new LinkedHashMap<>();
            diagnostics.put("expectedSource", "PYVRP_SEED");
            diagnostics.put("runtimeMs", elapsedMs(started));
            diagnostics.put("runnerRuntimeMs", result.path("runtimeMs").asLong(0));
            diagnostics.put("seedDistanceKm", seed.totalDistanceKm());
            diagnostics.put("seedLateCount", seed.lateOrderCount());
            diagnostics.put("routeCount", seed.routes().size());
            diagnostics.put("input", input.toString());
            diagnostics.put("output", output.toString());
            diagnostics.put("checkerStatus", result.path("status").asText("UNKNOWN"));
            diagnostics.put("checkerFeasible", result.path("checked").path("feasible").asBoolean(false));
            diagnostics.put("checkerViolations", result.path("checked").path("violations").toString());
            diagnostics.put("pyvrpFeasible", result.path("pyvrpFeasible").asBoolean(false));
            diagnostics.put("pyvrpVersion", result.path("pyvrpVersion").asText(""));
            String reason = "PASS".equalsIgnoreCase(result.path("status").asText())
                    ? "pyvrp-seed-emitted"
                    : "pyvrp-seed-emitted-with-checker-violations";
            return new ExternalSeedContribution(contributorId(), ExternalContributorStatus.OK, seed, reason, diagnostics);
        } catch (Exception exception) {
            return skipped("pyvrp-seed-error-" + exception.getClass().getSimpleName(), started, Map.of("error", exception.getMessage() == null ? "" : exception.getMessage()));
        }
    }

    private Map<String, Object> instance(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot) {
        Driver depotDriver = request.drivers().get(0);
        List<Map<String, Object>> nodes = new ArrayList<>();
        nodes.add(Map.of(
                "id", "DRIVER:" + depotDriver.driverId(),
                "x", depotDriver.currentLocation().longitude(),
                "y", depotDriver.currentLocation().latitude(),
                "demand", 0,
                "readyTime", 0,
                "dueTime", 1440,
                "serviceTime", 0));
        for (Order order : request.orders()) {
            nodes.add(Map.of(
                    "id", "PICKUP:" + order.orderId(),
                    "x", order.pickupPoint().longitude(),
                    "y", order.pickupPoint().latitude(),
                    "demand", 0,
                    "readyTime", 0,
                    "dueTime", Math.max(1, order.promisedEtaMinutes()),
                    "serviceTime", 1));
            nodes.add(Map.of(
                    "id", "DROPOFF:" + order.orderId(),
                    "x", order.dropoffPoint().longitude(),
                    "y", order.dropoffPoint().latitude(),
                    "demand", 0,
                    "readyTime", 0,
                    "dueTime", Math.max(1, order.promisedEtaMinutes()),
                    "serviceTime", 1));
        }
        MatrixCostAdapter matrix = new MatrixCostAdapter(matrixSnapshot);
        double[][] distances = new double[nodes.size()][nodes.size()];
        for (int from = 0; from < nodes.size(); from++) {
            for (int to = 0; to < nodes.size(); to++) {
                distances[from][to] = matrix.distanceKm(
                        (double) nodes.get(from).get("y"),
                        (double) nodes.get(from).get("x"),
                        (double) nodes.get(to).get("y"),
                        (double) nodes.get(to).get("x"));
            }
        }
        return Map.of(
                "schemaVersion", "irx-pyvrp-seed-instance/v1",
                "problemType", "VRPTW",
                "scenarioId", request.traceId(),
                "depotNodeId", "DRIVER:" + depotDriver.driverId(),
                "vehicleCount", request.drivers().size(),
                "capacity", Math.max(1, request.orders().size() * 2),
                "nodes", nodes,
                "distanceMatrix", distances);
    }

    private SolutionSeedCandidate seedFromResult(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot, JsonNode result) {
        Map<String, Order> orderById = new LinkedHashMap<>();
        request.orders().forEach(order -> orderById.put(order.orderId(), order));
        MatrixCostAdapter matrix = new MatrixCostAdapter(matrixSnapshot);
        Map<String, NodeCoord> coordinates = coordinates(request);
        List<SolutionSeedRoute> routes = new ArrayList<>();
        Set<String> assigned = new LinkedHashSet<>();
        int routeIndex = 0;
        for (JsonNode routeNode : result.path("routes")) {
            if (routeIndex >= request.drivers().size()) {
                break;
            }
            Driver driver = request.drivers().get(routeIndex);
            SolutionSeedRoute route = seedRoute(routeIndex, driver, routeNode, orderById, matrix, coordinates);
            routeIndex++;
            if (!route.orderIds().isEmpty()) {
                assigned.addAll(route.orderIds());
                routes.add(route);
            }
        }
        double totalKm = routes.stream().mapToDouble(SolutionSeedRoute::distanceKm).sum();
        long late = routes.stream().mapToLong(SolutionSeedRoute::lateOrderCount).sum();
        List<DriverSeedLoad> loads = routes.stream().map(route -> new DriverSeedLoad(route.driverId(), route.orderIds().size())).toList();
        double coverage = request.orders().isEmpty() ? 0.0 : assigned.size() / (double) request.orders().size();
        boolean fullCoverage = request.orders().isEmpty() || assigned.size() == request.orders().size();
        double score = coverage * 1_000_000.0 - Math.max(0, request.orders().size() - assigned.size()) * 1_000_000.0 - totalKm * 100.0 - late * 10_000.0;
        return new SolutionSeedCandidate(
                "SOL-PYVRP-SEED",
                CandidateSource.PYVRP_SEED,
                routes,
                coverage,
                round(totalKm),
                late,
                loads,
                !routes.isEmpty() && fullCoverage,
                routes.isEmpty() ? "empty-pyvrp-routes" : fullCoverage ? "" : "partial-pyvrp-coverage",
                List.of("pyvrp-external-seed-contributor", result.path("solver").asText("pyvrp")),
                new HybridCostBreakdown(round(totalKm), late * 10.0, 0.0, 0.0, 0.0, 0.0, score));
    }

    private Map<String, NodeCoord> coordinates(UnifiedDispatchRequest request) {
        Map<String, NodeCoord> coordinates = new LinkedHashMap<>();
        for (Driver driver : request.drivers()) {
            coordinates.put("DRIVER:" + driver.driverId(), new NodeCoord(driver.currentLocation().latitude(), driver.currentLocation().longitude()));
        }
        for (Order order : request.orders()) {
            coordinates.put("PICKUP:" + order.orderId(), new NodeCoord(order.pickupPoint().latitude(), order.pickupPoint().longitude()));
            coordinates.put("DROPOFF:" + order.orderId(), new NodeCoord(order.dropoffPoint().latitude(), order.dropoffPoint().longitude()));
        }
        return coordinates;
    }

    private SolutionSeedRoute seedRoute(int routeIndex, Driver driver, JsonNode routeNode, Map<String, Order> orderById, MatrixCostAdapter matrix, Map<String, NodeCoord> coordinates) {
        List<String> sequence = new ArrayList<>();
        Set<String> picked = new LinkedHashSet<>();
        Set<String> completed = new LinkedHashSet<>();
        String previous = "DRIVER:" + driver.driverId();
        double km = 0.0;
        double minutes = 0.0;
        long late = 0;
        for (JsonNode visitNode : routeNode) {
            String nodeId = visitNode.asText();
            if (nodeId.startsWith("DRIVER:")) {
                continue;
            }
            String[] parts = nodeId.split(":", 2);
            if (parts.length != 2 || !orderById.containsKey(parts[1])) {
                continue;
            }
            if ("DROPOFF".equals(parts[0]) && !picked.contains(parts[1])) {
                continue;
            }
            if ("PICKUP".equals(parts[0]) && picked.contains(parts[1])) {
                continue;
            }
            if ("DROPOFF".equals(parts[0]) && completed.contains(parts[1])) {
                continue;
            }
            NodeCoord from = coordinates.get(previous);
            NodeCoord to = coordinates.get(nodeId);
            if (from == null || to == null) {
                continue;
            }
            km += matrix.distanceKm(from.lat(), from.lng(), to.lat(), to.lng());
            minutes += matrix.durationMinutes(from.lat(), from.lng(), to.lat(), to.lng());
            previous = nodeId;
            sequence.add(nodeId);
            if ("PICKUP".equals(parts[0])) {
                picked.add(parts[1]);
            } else {
                completed.add(parts[1]);
                if (minutes > orderById.get(parts[1]).promisedEtaMinutes()) {
                    late++;
                }
            }
        }
        List<String> orderIds = completed.stream().toList();
        return new SolutionSeedRoute("PYVRP-R" + routeIndex, driver.driverId(), orderIds, sequence, round(km), round(minutes), late);
    }

    private ExternalSeedContribution skipped(String reason, long started, Map<String, Object> diagnostics) {
        Map<String, Object> copy = new LinkedHashMap<>(diagnostics);
        copy.put("runtimeMs", elapsedMs(started));
        return new ExternalSeedContribution(contributorId(), ExternalContributorStatus.EVIDENCE_GAP, null, reason, copy);
    }

    private long elapsedMs(long startedNanos) {
        return Math.max(0L, Duration.ofNanos(System.nanoTime() - startedNanos).toMillis());
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    private record NodeCoord(double lat, double lng) {
    }
}
