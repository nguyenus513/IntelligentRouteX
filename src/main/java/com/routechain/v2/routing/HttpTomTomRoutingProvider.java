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

public final class HttpTomTomRoutingProvider implements RoutingProvider {
    private static final String ROUTE_PATH = "routing/1/calculateRoute/";
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI baseUri;
    private final String apiKey;
    private final Duration readTimeout;
    private final RouteCostFunction routeCostFunction;
    private final RoutingProvider fallbackProvider;

    public HttpTomTomRoutingProvider(String baseUrl,
                                     String apiKey,
                                     Duration connectTimeout,
                                     Duration readTimeout,
                                     RouteCostFunction routeCostFunction,
                                     RoutingProvider fallbackProvider) {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
        this.objectMapper = JsonMapper.builder().findAndAddModules().build();
        this.baseUri = URI.create((baseUrl == null || baseUrl.isBlank() ? "https://api.tomtom.com" : baseUrl).endsWith("/")
                ? (baseUrl == null || baseUrl.isBlank() ? "https://api.tomtom.com/" : baseUrl)
                : baseUrl + "/");
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.readTimeout = readTimeout == null ? Duration.ofSeconds(3) : readTimeout;
        this.routeCostFunction = routeCostFunction;
        this.fallbackProvider = fallbackProvider;
    }

    @Override
    public String providerId() {
        return "tomtom-routing";
    }

    @Override
    public boolean ready() {
        return !apiKey.isBlank();
    }

    @Override
    public RoutingSnapResult snap(RouteStop stop) {
        if (!ready()) {
            return fallbackProvider.snap(stop);
        }
        return new RoutingSnapResult(
                "routing-snap-result/v1",
                providerId(),
                "TOMTOM_ROUTE_ENDPOINT_SNAP_PENDING",
                stop.latitude(),
                stop.longitude(),
                stop.latitude(),
                stop.longitude(),
                0.0,
                0.75,
                stop.stopId(),
                stop.stopId(),
                List.of("tomtom-dedicated-snap-not-yet-integrated"));
    }

    @Override
    public RoutingRouteResult route(BestPathRequest request) {
        if (!ready()) {
            return fallback("tomtom-routing-api-key-missing", request);
        }
        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(buildRouteUri(request))
                    .timeout(readTimeout)
                    .GET()
                    .build();
            HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return fallback("tomtom-routing-http-" + response.statusCode(), request);
            }
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode route = root.path("routes").path(0);
            if (route.isMissingNode() || route.path("legs").isEmpty()) {
                return fallback("tomtom-routing-no-route", request);
            }
            List<RoutePolylinePoint> polyline = polyline(route);
            if (polyline.size() < 2) {
                return fallback("tomtom-routing-empty-polyline", request);
            }
            double distanceMeters = positive(route.path("summary").path("lengthInMeters").asDouble(0.0), directDistance(polyline));
            double travelSeconds = positive(route.path("summary").path("travelTimeInSeconds").asDouble(0.0), distanceMeters / 7.2);
            int turnCount = Math.max(1, Math.min(80, polyline.size() / 3));
            double avgSpeed = distanceMeters / Math.max(1.0, travelSeconds);
            double straightness = clamp(directDistance(polyline) / Math.max(1.0, distanceMeters));
            double congestionScore = clamp(route.path("summary").path("trafficDelayInSeconds").asDouble(0.0) / Math.max(1.0, travelSeconds));
            double bearing = bearingDegrees(polyline.getFirst().latitude(), polyline.getFirst().longitude(), polyline.getLast().latitude(), polyline.getLast().longitude());
            double routeCost = routeCostFunction.score(travelSeconds, congestionScore, 0.25, turnCount, 0, 0.7, straightness, distanceMeters);
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
                    congestionScore,
                    clamp((turnCount / Math.max(1.0, distanceMeters / 1000.0)) / 20.0),
                    routeCost,
                    providerId(),
                    "tomtom-road-polyline",
                    polyline,
                    "");
            return new RoutingRouteResult(
                    "routing-route-result/v1",
                    providerId(),
                    "tomtom-road-polyline",
                    leg,
                    0.7,
                    polyline,
                    List.of());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return fallback("tomtom-routing-interrupted", request);
        } catch (IOException | RuntimeException exception) {
            return fallback("tomtom-routing-unavailable", request);
        }
    }

    private URI buildRouteUri(BestPathRequest request) {
        String locations = "%s,%s:%s,%s".formatted(
                request.fromStop().latitude(),
                request.fromStop().longitude(),
                request.toStop().latitude(),
                request.toStop().longitude());
        String query = "routeRepresentation=polyline&travelMode=car&computeTravelTimeFor=all&key=%s".formatted(encode(apiKey));
        return baseUri.resolve(ROUTE_PATH + locations + "/json?" + query);
    }

    private List<RoutePolylinePoint> polyline(JsonNode route) {
        List<RoutePolylinePoint> points = new ArrayList<>();
        for (JsonNode leg : route.path("legs")) {
            for (JsonNode point : leg.path("points")) {
                double latitude = point.path("latitude").asDouble(Double.NaN);
                double longitude = point.path("longitude").asDouble(Double.NaN);
                if (Double.isFinite(latitude) && Double.isFinite(longitude)) {
                    points.add(new RoutePolylinePoint(latitude, longitude, "road"));
                }
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

    private String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
