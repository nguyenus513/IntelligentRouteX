package com.routechain.v2.routing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

public final class OsrmTableClient {
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI baseUri;
    private final Duration readTimeout;
    private final DurationMatrixCache cache;

    public OsrmTableClient(String baseUrl, Duration connectTimeout, Duration readTimeout, DurationMatrixCache cache) {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout == null ? Duration.ofSeconds(2) : connectTimeout)
                .build();
        this.objectMapper = JsonMapper.builder().findAndAddModules().build();
        String safeBaseUrl = baseUrl == null || baseUrl.isBlank() ? "http://127.0.0.1:5000" : baseUrl;
        this.baseUri = URI.create(safeBaseUrl.endsWith("/") ? safeBaseUrl : safeBaseUrl + "/");
        this.readTimeout = readTimeout == null ? Duration.ofSeconds(5) : readTimeout;
        this.cache = cache == null ? new DurationMatrixCache() : cache;
    }

    public String providerId() {
        return "osrm-table";
    }

    public DurationMatrix fetchMatrix(List<RouteStop> sources, List<RouteStop> destinations) {
        List<RouteStop> safeSources = sources == null ? List.of() : List.copyOf(sources);
        List<RouteStop> safeDestinations = destinations == null ? List.of() : List.copyOf(destinations);
        DurationMatrix cached = cache.get(providerId(), safeSources, safeDestinations);
        if (cached != null) {
            return cached;
        }
        long started = System.nanoTime();
        try {
            DurationMatrix matrix = fetchUncached(safeSources, safeDestinations, started);
            cache.put(providerId(), safeSources, safeDestinations, matrix);
            return matrix;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return failed(safeSources, safeDestinations, started, "osrm-table-interrupted");
        } catch (IOException exception) {
            return failed(safeSources, safeDestinations, started, "osrm-table-io-" + safeReason(exception.getClass().getSimpleName()));
        } catch (RuntimeException exception) {
            return failed(safeSources, safeDestinations, started, "osrm-table-runtime-" + safeReason(exception.getClass().getSimpleName()));
        }
    }

    public DurationMatrixCache cache() {
        return cache;
    }

    private DurationMatrix fetchUncached(List<RouteStop> sources, List<RouteStop> destinations, long started) throws IOException, InterruptedException {
        if (sources.isEmpty() || destinations.isEmpty()) {
            return failed(sources, destinations, started, "osrm-table-empty-input");
        }
        List<RouteStop> allStops = new ArrayList<>(sources.size() + destinations.size());
        allStops.addAll(sources);
        allStops.addAll(destinations);
        String coordinates = allStops.stream()
                .map(stop -> stop.longitude() + "," + stop.latitude())
                .collect(java.util.stream.Collectors.joining(";"));
        String sourceIndexes = java.util.stream.IntStream.range(0, sources.size())
                .mapToObj(String::valueOf)
                .collect(java.util.stream.Collectors.joining(";"));
        String destinationIndexes = java.util.stream.IntStream.range(sources.size(), allStops.size())
                .mapToObj(String::valueOf)
                .collect(java.util.stream.Collectors.joining(";"));
        String query = "annotations=duration,distance&sources=" + sourceIndexes + "&destinations=" + destinationIndexes;
        URI uri = baseUri.resolve("table/v1/driving/" + encodePath(coordinates) + "?" + query);
        HttpRequest request = HttpRequest.newBuilder(uri).timeout(readTimeout).GET().build();
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            return failed(sources, destinations, started, "osrm-table-http-" + response.statusCode());
        }
        JsonNode root = objectMapper.readTree(response.body());
        String code = root.path("code").asText("Ok");
        if (!"Ok".equalsIgnoreCase(code)) {
            return failed(sources, destinations, started, "osrm-table-code-" + safeReason(code));
        }
        return new DurationMatrix(
                "duration-matrix/v1",
                providerId(),
                sources,
                destinations,
                parsePoints(sources, root.path("sources")),
                parsePoints(destinations, root.path("destinations")),
                parseMatrix(root.path("durations")),
                parseMatrix(root.path("distances")),
                countNull(root.path("durations")),
                countNull(root.path("distances")),
                elapsedMs(started),
                List.of());
    }

    private List<MatrixPoint> parsePoints(List<RouteStop> rawStops, JsonNode nodes) {
        List<MatrixPoint> points = new ArrayList<>(rawStops.size());
        for (int index = 0; index < rawStops.size(); index++) {
            RouteStop stop = rawStops.get(index);
            JsonNode node = nodes.path(index);
            JsonNode location = node.path("location");
            if (!location.isArray() || location.size() < 2) {
                points.add(MatrixPoint.unsnapped(stop, "osrm-table-snap-missing"));
                continue;
            }
            double snappedLon = location.path(0).asDouble(stop.longitude());
            double snappedLat = location.path(1).asDouble(stop.latitude());
            points.add(new MatrixPoint(
                    stop.stopId(),
                    stop.latitude(),
                    stop.longitude(),
                    snappedLat,
                    snappedLon,
                    node.path("distance").asDouble(0.0),
                    node.path("name").asText(""),
                    List.of()));
        }
        return List.copyOf(points);
    }

    private List<List<Double>> parseMatrix(JsonNode matrixNode) {
        List<List<Double>> rows = new ArrayList<>();
        for (JsonNode rowNode : matrixNode) {
            List<Double> row = new ArrayList<>();
            for (JsonNode cell : rowNode) {
                row.add(cell == null || cell.isNull() ? null : cell.asDouble());
            }
            rows.add(java.util.Collections.unmodifiableList(row));
        }
        return java.util.Collections.unmodifiableList(rows);
    }

    private int countNull(JsonNode matrixNode) {
        int count = 0;
        for (JsonNode rowNode : matrixNode) {
            for (JsonNode cell : rowNode) {
                if (cell == null || cell.isNull()) {
                    count++;
                }
            }
        }
        return count;
    }

    private DurationMatrix failed(List<RouteStop> sources, List<RouteStop> destinations, long started, String reason) {
        return new DurationMatrix(
                "duration-matrix/v1",
                providerId(),
                sources,
                destinations,
                sources.stream().map(source -> MatrixPoint.unsnapped(source, reason)).toList(),
                destinations.stream().map(destination -> MatrixPoint.unsnapped(destination, reason)).toList(),
                List.of(),
                List.of(),
                sources.size() * destinations.size(),
                sources.size() * destinations.size(),
                elapsedMs(started),
                List.of(reason));
    }

    private long elapsedMs(long started) {
        return Math.max(0L, Duration.ofNanos(System.nanoTime() - started).toMillis());
    }

    private String encodePath(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8)
                .replace("%3B", ";")
                .replace("%2C", ",");
    }

    private String safeReason(String value) {
        if (value == null || value.isBlank()) {
            return "unknown";
        }
        return value.toLowerCase().replaceAll("[^a-z0-9-]", "-");
    }
}
