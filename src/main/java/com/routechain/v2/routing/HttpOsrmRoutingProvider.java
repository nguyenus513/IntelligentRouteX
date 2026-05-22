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

public final class HttpOsrmRoutingProvider implements RoutingProvider {
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI baseUri;
    private final Duration readTimeout;
    private final RouteCostFunction routeCostFunction;
    private final RoutingProvider fallbackProvider;

    public HttpOsrmRoutingProvider(String baseUrl,
                                   Duration connectTimeout,
                                   Duration readTimeout,
                                   RouteCostFunction routeCostFunction,
                                   RoutingProvider fallbackProvider) {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout == null ? Duration.ofSeconds(2) : connectTimeout)
                .build();
        this.objectMapper = JsonMapper.builder().findAndAddModules().build();
        String safeBaseUrl = baseUrl == null || baseUrl.isBlank() ? "http://127.0.0.1:5000" : baseUrl;
        this.baseUri = URI.create(safeBaseUrl.endsWith("/") ? safeBaseUrl : safeBaseUrl + "/");
        this.readTimeout = readTimeout == null ? Duration.ofSeconds(5) : readTimeout;
        this.routeCostFunction = routeCostFunction;
        this.fallbackProvider = fallbackProvider;
    }

    @Override
    public String providerId() {
        return "osrm-routing";
    }

    @Override
    public boolean ready() {
        return true;
    }

    @Override
    public RoutingSnapResult snap(RouteStop stop) {
        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(buildNearestUri(stop))
                    .timeout(readTimeout)
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return snapFallback(stop, "osrm-nearest-http-" + response.statusCode());
            }
            JsonNode root = objectMapper.readTree(response.body());
            String code = root.path("code").asText("Ok");
            if (!"Ok".equalsIgnoreCase(code)) {
                return snapFallback(stop, "osrm-nearest-code-" + safeReason(code));
            }
            JsonNode waypoint = root.path("waypoints").path(0);
            JsonNode location = waypoint.path("location");
            if (!location.isArray() || location.size() < 2) {
                return snapFallback(stop, "osrm-nearest-location-missing");
            }
            double snappedLongitude = location.path(0).asDouble(stop.longitude());
            double snappedLatitude = location.path(1).asDouble(stop.latitude());
            double distance = waypoint.path("distance").asDouble(0.0);
            return new RoutingSnapResult(
                    "routing-snap-result/v1",
                    providerId(),
                    "SNAPPED",
                    stop.latitude(),
                    stop.longitude(),
                    snappedLatitude,
                    snappedLongitude,
                    distance,
                    clamp(1.0 - (distance / 100.0)),
                    waypoint.path("name").asText(stop.stopId()),
                    waypoint.path("hint").asText(stop.stopId()),
                    List.of());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return snapFallback(stop, "osrm-nearest-interrupted");
        } catch (IOException exception) {
            return snapFallback(stop, "osrm-nearest-io-" + safeReason(exception.getClass().getSimpleName()));
        } catch (RuntimeException exception) {
            return snapFallback(stop, "osrm-nearest-runtime-" + safeReason(exception.getClass().getSimpleName()));
        }
    }

    @Override
    public RoutingRouteResult route(BestPathRequest request) {
        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(buildRouteUri(request))
                    .timeout(readTimeout)
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return fallback("osrm-routing-http-" + response.statusCode(), request);
            }
            JsonNode root = objectMapper.readTree(response.body());
            String code = root.path("code").asText("Ok");
            if (!"Ok".equalsIgnoreCase(code)) {
                return fallback("osrm-routing-code-" + safeReason(code), request);
            }
            JsonNode route = root.path("routes").path(0);
            if (route.isMissingNode()) {
                return fallback("osrm-routing-no-route", request);
            }
            List<RoutePolylinePoint> polyline = polyline(route);
            if (polyline.size() < 2) {
                return fallback("osrm-routing-empty-polyline", request);
            }
            double distanceMeters = positive(route.path("distance").asDouble(0.0), directDistance(polyline));
            double travelSeconds = positive(route.path("duration").asDouble(0.0), distanceMeters / 7.2);
            int turnCount = Math.max(1, Math.min(80, Math.max(1, polyline.size() / 4)));
            double avgSpeed = distanceMeters / Math.max(1.0, travelSeconds);
            double straightness = clamp(directDistance(polyline) / Math.max(1.0, distanceMeters));
            double bearing = bearingDegrees(polyline.getFirst().latitude(), polyline.getFirst().longitude(), polyline.getLast().latitude(), polyline.getLast().longitude());
            double routeCost = routeCostFunction.score(travelSeconds, 0.0, 0.20, turnCount, 0, 0.72, straightness, distanceMeters);
            LegRouteVector leg = new LegRouteVector(
                    "route-leg-vector/v1",
                    request.fromStop().stopId(),
                    request.toStop().stopId(),
                    request.toStop().latitude() - request.fromStop().latitude(),
                    request.toStop().longitude() - request.fromStop().longitude(),
                    bearing,
                    bearing,
                    bearing,
                    distanceMeters,
                    travelSeconds,
                    avgSpeed,
                    0.75,
                    0.25,
                    turnCount,
                    turnCount / 2,
                    Math.max(0, turnCount - (turnCount / 2)),
                    0,
                    straightness,
                    0.0,
                    clamp((turnCount / Math.max(1.0, distanceMeters / 1000.0)) / 20.0),
                    routeCost,
                    providerId(),
                    "osrm-road-polyline",
                    polyline,
                    "");
            return new RoutingRouteResult(
                    "routing-route-result/v1",
                    providerId(),
                    "osrm-road-polyline",
                    leg,
                    0.72,
                    polyline,
                    List.of());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return fallback("osrm-routing-interrupted", request);
        } catch (IOException exception) {
            return fallback("osrm-routing-io-" + safeReason(exception.getClass().getSimpleName()), request);
        } catch (RuntimeException exception) {
            return fallback("osrm-routing-runtime-" + safeReason(exception.getClass().getSimpleName()), request);
        }
    }

    private URI buildRouteUri(BestPathRequest request) {
        String coordinates = "%s,%s;%s,%s".formatted(
                request.fromStop().longitude(),
                request.fromStop().latitude(),
                request.toStop().longitude(),
                request.toStop().latitude());
        String query = "overview=simplified&geometries=geojson&steps=false&annotations=false";
        return baseUri.resolve("route/v1/driving/" + encodePath(coordinates) + "?" + query);
    }

    private URI buildNearestUri(RouteStop stop) {
        String coordinates = "%s,%s".formatted(stop.longitude(), stop.latitude());
        return baseUri.resolve("nearest/v1/driving/" + encodePath(coordinates) + "?number=1");
    }

    private RoutingSnapResult snapFallback(RouteStop stop, String reason) {
        return new RoutingSnapResult(
                "routing-snap-result/v1",
                providerId(),
                "FALLBACK_RAW_POINT",
                stop.latitude(),
                stop.longitude(),
                stop.latitude(),
                stop.longitude(),
                0.0,
                0.0,
                stop.stopId(),
                stop.stopId(),
                List.of(reason));
    }

    private List<RoutePolylinePoint> polyline(JsonNode route) {
        List<RoutePolylinePoint> points = new ArrayList<>();
        for (JsonNode coordinate : route.path("geometry").path("coordinates")) {
            if (!coordinate.isArray() || coordinate.size() < 2) {
                continue;
            }
            double longitude = coordinate.path(0).asDouble(Double.NaN);
            double latitude = coordinate.path(1).asDouble(Double.NaN);
            if (Double.isFinite(latitude) && Double.isFinite(longitude)) {
                points.add(new RoutePolylinePoint(latitude, longitude, "osm-road"));
            }
        }
        return List.copyOf(points);
    }

    private RoutingRouteResult fallback(String reason, BestPathRequest request) {
        RoutingRouteResult fallback = fallbackProvider.route(request);
        LegRouteVector leg = fallback.legVector().withRoutingGeometry(
                fallback.legVector().routingProvider(),
                fallback.legVector().geometryKind(),
                fallback.polyline(),
                reason);
        List<String> reasons = new ArrayList<>(fallback.degradeReasons());
        reasons.add(reason);
        return new RoutingRouteResult(fallback.schemaVersion(), fallback.provider(), fallback.geometryKind(), leg, fallback.corridorPreferenceScore(), fallback.polyline(), reasons);
    }

    private double directDistance(List<RoutePolylinePoint> points) {
        if (points.size() < 2) {
            return 0.0;
        }
        RoutePolylinePoint first = points.getFirst();
        RoutePolylinePoint last = points.getLast();
        return haversineMeters(first.latitude(), first.longitude(), last.latitude(), last.longitude());
    }

    private double haversineMeters(double lat1, double lon1, double lat2, double lon2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return 6_371_000.0 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private double bearingDegrees(double lat1, double lon1, double lat2, double lon2) {
        double y = Math.sin(Math.toRadians(lon2 - lon1)) * Math.cos(Math.toRadians(lat2));
        double x = Math.cos(Math.toRadians(lat1)) * Math.sin(Math.toRadians(lat2))
                - Math.sin(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) * Math.cos(Math.toRadians(lon2 - lon1));
        return (Math.toDegrees(Math.atan2(y, x)) + 360.0) % 360.0;
    }

    private double positive(double value, double fallback) {
        return Double.isFinite(value) && value > 0.0 ? value : fallback;
    }

    private double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
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
