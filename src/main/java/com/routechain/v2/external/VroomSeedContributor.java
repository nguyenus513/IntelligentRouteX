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

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
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

public final class VroomSeedContributor implements ExternalSeedContributor {
    private static final ObjectMapper OBJECT_MAPPER = JsonMapper.builder().findAndAddModules().build();

    @Override
    public String contributorId() {
        return "VROOM";
    }

    @Override
    public ExternalSeedContribution contribute(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot) {
        long started = System.nanoTime();
        if (request == null || request.orders().isEmpty() || request.drivers().isEmpty() || matrixSnapshot == null) {
            return skipped("missing-request-or-matrix", started, Map.of("expectedSource", "VROOM_SEED"));
        }
        String baseUrl = System.getenv("VROOM_BASE_URL");
        String bin = System.getenv("VROOM_BIN");
        if ((baseUrl == null || baseUrl.isBlank()) && (bin == null || bin.isBlank())) {
            return skipped("vroom-runtime-not-configured", started, Map.of("expectedSource", "VROOM_SEED", "supportedModes", List.of("VROOM_BASE_URL", "VROOM_BIN")));
        }
        try {
            Map<String, Object> payload = vroomRequest(request, matrixSnapshot);
            JsonNode response = baseUrl != null && !baseUrl.isBlank()
                    ? runHttp(baseUrl, payload)
                    : runBinary(bin, payload, request.traceId());
            if (response == null || response.path("routes").isMissingNode() || response.path("routes").isEmpty()) {
                return skipped("vroom-no-routes", started, Map.of("expectedSource", "VROOM_SEED"));
            }
            SolutionSeedCandidate seed = seedFromResponse(request, matrixSnapshot, response);
            if (seed.routes().isEmpty()) {
                return skipped("vroom-empty-seed-after-pd-filter", started, Map.of("expectedSource", "VROOM_SEED"));
            }
            Map<String, Object> diagnostics = new LinkedHashMap<>();
            diagnostics.put("expectedSource", "VROOM_SEED");
            diagnostics.put("runtimeMs", elapsedMs(started));
            diagnostics.put("seedDistanceKm", seed.totalDistanceKm());
            diagnostics.put("seedLateCount", seed.lateOrderCount());
            diagnostics.put("routeCount", seed.routes().size());
            diagnostics.put("mode", baseUrl != null && !baseUrl.isBlank() ? "HTTP" : "BINARY");
            diagnostics.put("summary", OBJECT_MAPPER.convertValue(response.path("summary"), Map.class));
            return new ExternalSeedContribution(contributorId(), ExternalContributorStatus.OK, seed, "vroom-seed-emitted", diagnostics);
        } catch (Exception exception) {
            return skipped("vroom-seed-error-" + exception.getClass().getSimpleName(), started, Map.of("error", exception.getMessage() == null ? "" : exception.getMessage()));
        }
    }

    private JsonNode runHttp(String baseUrl, Map<String, Object> payload) throws Exception {
        String url = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(OBJECT_MAPPER.writeValueAsString(payload)))
                .build();
        HttpResponse<String> response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException("vroom-http-status-" + response.statusCode());
        }
        return OBJECT_MAPPER.readTree(response.body());
    }

    private JsonNode runBinary(String bin, Map<String, Object> payload, String traceId) throws Exception {
        Path root = Path.of("artifacts", "external-seeds", "vroom");
        Files.createDirectories(root);
        String trace = traceId == null || traceId.isBlank() ? "run" : traceId.replaceAll("[^A-Za-z0-9_-]", "_");
        Path input = root.resolve(trace + "-input.json");
        Path output = root.resolve(trace + "-output.json");
        OBJECT_MAPPER.writeValue(input.toFile(), payload);
        Process process = new ProcessBuilder(bin, "-i", input.toString(), "-o", output.toString())
                .redirectErrorStream(true)
                .start();
        boolean completed = process.waitFor(35, TimeUnit.SECONDS);
        if (!completed) {
            process.destroyForcibly();
            throw new IllegalStateException("vroom-binary-timeout");
        }
        if (process.exitValue() != 0 || !Files.exists(output)) {
            String text = new String(process.getInputStream().readAllBytes());
            throw new IllegalStateException("vroom-binary-failed:" + text);
        }
        return OBJECT_MAPPER.readTree(output.toFile());
    }

    private Map<String, Object> vroomRequest(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot) {
        Map<String, NodeCoord> coordinates = coordinates(request);
        List<NodeCoord> indexedCoordinates = new ArrayList<>(coordinates.values());
        Map<String, Integer> locationIndex = new LinkedHashMap<>();
        int index = 0;
        for (String key : coordinates.keySet()) {
            locationIndex.put(key, index++);
        }
        MatrixCostAdapter matrix = new MatrixCostAdapter(matrixSnapshot);

        List<Map<String, Object>> vehicles = new ArrayList<>();
        int vehicleIndex = 1;
        for (Driver driver : request.drivers()) {
            vehicles.add(Map.of(
                    "id", vehicleIndex++,
                    "description", driver.driverId(),
                    "start_index", locationIndex.get("DRIVER:" + driver.driverId()),
                    "capacity", List.of(Math.max(1, request.orders().size()))));
        }
        List<Map<String, Object>> shipments = new ArrayList<>();
        int shipmentIndex = 1;
        for (Order order : request.orders()) {
            shipments.add(Map.of(
                    "id", shipmentIndex++,
                    "amount", List.of(1),
                    "pickup", Map.of(
                            "id", shipmentIndex * 10 + 1,
                            "description", "PICKUP:" + order.orderId(),
                            "location_index", locationIndex.get("PICKUP:" + order.orderId()),
                            "time_windows", List.of(List.of(0, Math.max(60, order.promisedEtaMinutes() * 60)))),
                    "delivery", Map.of(
                            "id", shipmentIndex * 10 + 2,
                            "description", "DROPOFF:" + order.orderId(),
                            "location_index", locationIndex.get("DROPOFF:" + order.orderId()),
                            "time_windows", List.of(List.of(0, Math.max(60, order.promisedEtaMinutes() * 60))))));
        }
        List<List<Long>> durations = new ArrayList<>();
        List<List<Long>> distances = new ArrayList<>();
        for (NodeCoord from : indexedCoordinates) {
            List<Long> durationRow = new ArrayList<>();
            List<Long> distanceRow = new ArrayList<>();
            for (NodeCoord to : indexedCoordinates) {
                durationRow.add(Math.max(0L, Math.round(matrix.durationMinutes(from.lat(), from.lng(), to.lat(), to.lng()) * 60.0)));
                distanceRow.add(Math.max(0L, Math.round(matrix.distanceKm(from.lat(), from.lng(), to.lat(), to.lng()) * 1000.0)));
            }
            durations.add(durationRow);
            distances.add(distanceRow);
        }
        Map<String, Object> options = Map.of("g", false);
        return Map.of(
                "vehicles", vehicles,
                "shipments", shipments,
                "options", options,
                "matrices", Map.of("car", Map.of("durations", durations, "distances", distances)),
                "_irxMatrix", Map.of("routingMode", matrixSnapshot.routingMode(), "customMatrix", true));
    }

    private SolutionSeedCandidate seedFromResponse(UnifiedDispatchRequest request, DistanceDurationMatrixSnapshot matrixSnapshot, JsonNode response) {
        Map<Integer, String> orderByShipment = new LinkedHashMap<>();
        int shipmentIndex = 1;
        for (Order order : request.orders()) {
            orderByShipment.put(shipmentIndex++, order.orderId());
        }
        Map<String, Order> orderById = new LinkedHashMap<>();
        request.orders().forEach(order -> orderById.put(order.orderId(), order));
        Map<String, NodeCoord> coordinates = coordinates(request);
        MatrixCostAdapter matrix = new MatrixCostAdapter(matrixSnapshot);
        List<SolutionSeedRoute> routes = new ArrayList<>();
        Set<String> assigned = new LinkedHashSet<>();
        for (JsonNode routeNode : response.path("routes")) {
            String driverId = routeNode.path("description").asText("");
            if (driverId.isBlank()) {
                int vehicleId = routeNode.path("vehicle").asInt(1);
                if (vehicleId >= 1 && vehicleId <= request.drivers().size()) {
                    driverId = request.drivers().get(vehicleId - 1).driverId();
                }
            }
            if (driverId.isBlank()) {
                continue;
            }
            SolutionSeedRoute route = seedRoute(driverId, routeNode.path("steps"), orderByShipment, orderById, coordinates, matrix);
            if (!route.orderIds().isEmpty()) {
                assigned.addAll(route.orderIds());
                routes.add(route);
            }
        }
        double totalKm = routes.stream().mapToDouble(SolutionSeedRoute::distanceKm).sum();
        long late = routes.stream().mapToLong(SolutionSeedRoute::lateOrderCount).sum();
        double coverage = request.orders().isEmpty() ? 0.0 : assigned.size() / (double) request.orders().size();
        double score = coverage * 1_000_000.0 - Math.max(0, request.orders().size() - assigned.size()) * 1_000_000.0 - totalKm * 100.0 - late * 10_000.0;
        return new SolutionSeedCandidate(
                "SOL-VROOM-SEED",
                CandidateSource.VROOM_SEED,
                routes,
                coverage,
                round(totalKm),
                late,
                routes.stream().map(route -> new DriverSeedLoad(route.driverId(), route.orderIds().size())).toList(),
                !routes.isEmpty(),
                routes.isEmpty() ? "empty-vroom-routes" : "",
                List.of("vroom-external-seed-contributor"),
                new HybridCostBreakdown(round(totalKm), late * 10.0, 0.0, 0.0, 0.0, 0.0, score));
    }

    private SolutionSeedRoute seedRoute(String driverId,
                                        JsonNode steps,
                                        Map<Integer, String> orderByShipment,
                                        Map<String, Order> orderById,
                                        Map<String, NodeCoord> coordinates,
                                        MatrixCostAdapter matrix) {
        List<String> sequence = new ArrayList<>();
        Set<String> picked = new LinkedHashSet<>();
        Set<String> completed = new LinkedHashSet<>();
        String previous = "DRIVER:" + driverId;
        double km = 0.0;
        double minutes = 0.0;
        long late = 0;
        for (JsonNode step : steps) {
            String type = step.path("type").asText("");
            if (!"pickup".equals(type) && !"delivery".equals(type)) {
                continue;
            }
            String orderId = orderByShipment.get(step.path("id").asInt());
            if (orderId == null) {
                orderId = orderIdFromDescription(step.path("description").asText(""));
            }
            if (orderId == null || !orderById.containsKey(orderId)) {
                continue;
            }
            String nodeId = ("pickup".equals(type) ? "PICKUP:" : "DROPOFF:") + orderId;
            if ("delivery".equals(type) && !picked.contains(orderId)) {
                continue;
            }
            if ("pickup".equals(type) && picked.contains(orderId)) {
                continue;
            }
            NodeCoord from = coordinates.get(previous);
            NodeCoord to = coordinates.get(nodeId);
            if (from == null || to == null) {
                continue;
            }
            km += matrix.distanceKm(from.lat(), from.lng(), to.lat(), to.lng());
            minutes += matrix.durationMinutes(from.lat(), from.lng(), to.lat(), to.lng());
            sequence.add(nodeId);
            previous = nodeId;
            if ("pickup".equals(type)) {
                picked.add(orderId);
            } else {
                completed.add(orderId);
                if (minutes > orderById.get(orderId).promisedEtaMinutes()) {
                    late++;
                }
            }
        }
        return new SolutionSeedRoute("VROOM-" + driverId, driverId, completed.stream().toList(), sequence, round(km), round(minutes), late);
    }

    private String orderIdFromDescription(String description) {
        if (description == null || !description.contains(":")) {
            return null;
        }
        return description.substring(description.indexOf(':') + 1);
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
