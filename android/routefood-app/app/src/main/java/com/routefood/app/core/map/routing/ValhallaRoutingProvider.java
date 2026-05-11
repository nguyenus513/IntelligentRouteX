package com.routefood.app.core.map.routing;

import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.BuildConfig;
import com.routefood.app.data.model.GeoPoint;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ValhallaRoutingProvider implements RoutingProvider {
    private static final String DEFAULT_BASE_URL = "http://10.0.2.2:8002";
    private final String baseUrl;

    public ValhallaRoutingProvider() {
        this(BuildConfig.VALHALLA_BASE_URL == null || BuildConfig.VALHALLA_BASE_URL.isBlank() ? DEFAULT_BASE_URL : BuildConfig.VALHALLA_BASE_URL);
    }

    public ValhallaRoutingProvider(String baseUrl) {
        this.baseUrl = stripTrailingSlash(baseUrl);
    }

    @Override
    public RoadRoute routeFixedOrder(List<GeoPoint> rawWaypoints) throws Exception {
        if (rawWaypoints == null || rawWaypoints.size() < 2) {
            List<GeoPoint> safe = rawWaypoints == null ? new ArrayList<>() : new ArrayList<>(rawWaypoints);
            return fallbackRoadRoute(safe, "Not enough waypoints");
        }
        JSONObject request = buildRequest(rawWaypoints);
        JSONObject response = postRoute(request);
        List<GeoPoint> coordinates = parseCoordinates(response, rawWaypoints);
        List<OsrmRouteClient.NavigationInstruction> instructions = parseInstructions(response);
        double distanceMeters = parseDistanceMeters(response);
        double durationSeconds = parseDurationSeconds(response);
        RouteQuality quality = new RouteQuality(
                "valhalla",
                0.0,
                !coordinates.isEmpty(),
                true,
                Collections.emptyList()
        );
        return new RoadRoute(
                "valhalla_motor_scooter_v2",
                coordinates.size() >= 2,
                coordinates,
                instructions,
                Collections.emptyList(),
                distanceMeters,
                durationSeconds,
                quality
        );
    }

    private JSONObject buildRequest(List<GeoPoint> rawWaypoints) throws Exception {
        JSONArray locations = new JSONArray();
        for (GeoPoint waypoint : rawWaypoints) {
            locations.put(new JSONObject()
                    .put("lat", waypoint.latitude())
                    .put("lon", waypoint.longitude())
                    .put("type", "break"));
        }
        JSONObject costingOptions = new JSONObject()
                .put("motor_scooter", new JSONObject()
                        .put("use_highways", 0.05)
                        .put("use_tolls", 0.0)
                        .put("top_speed", 60));
        return new JSONObject()
                .put("locations", locations)
                .put("costing", "motor_scooter")
                .put("costing_options", costingOptions)
                .put("directions_options", new JSONObject()
                        .put("units", "kilometers"))
                .put("shape_format", "geojson");
    }

    private JSONObject postRoute(JSONObject request) throws Exception {
        URL url = new URL(baseUrl + "/route");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(8000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setRequestProperty("User-Agent", "RouteFoodDemo/0.1 Android IntelligentRouteX");
        byte[] body = request.toString().getBytes(StandardCharsets.UTF_8);
        try (OutputStream outputStream = connection.getOutputStream()) {
            outputStream.write(body);
        }
        int responseCode = connection.getResponseCode();
        if (responseCode < 200 || responseCode >= 300) {
            throw new IllegalStateException("Valhalla route failed with HTTP " + responseCode);
        }
        StringBuilder response = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) response.append(line);
        }
        return new JSONObject(response.toString());
    }

    private List<GeoPoint> parseCoordinates(JSONObject response, List<GeoPoint> fallback) throws Exception {
        Object shape = null;
        JSONObject trip = response.optJSONObject("trip");
        if (trip != null) shape = trip.opt("shape");
        if (shape instanceof JSONObject) {
            JSONObject shapeObject = (JSONObject) shape;
            JSONArray coordinates = shapeObject.optJSONArray("coordinates");
            if (coordinates != null) return parseLngLatArray(coordinates);
        }
        if (shape instanceof JSONArray) return parseLngLatArray((JSONArray) shape);
        JSONArray routes = response.optJSONArray("routes");
        if (routes != null && routes.length() > 0) {
            JSONObject geometry = routes.getJSONObject(0).optJSONObject("geometry");
            if (geometry != null) return parseLngLatArray(geometry.getJSONArray("coordinates"));
        }
        return new ArrayList<>(fallback);
    }

    private List<GeoPoint> parseLngLatArray(JSONArray coordinates) throws Exception {
        List<GeoPoint> points = new ArrayList<>();
        for (int index = 0; index < coordinates.length(); index++) {
            JSONArray coordinate = coordinates.getJSONArray(index);
            points.add(new GeoPoint(coordinate.getDouble(1), coordinate.getDouble(0)));
        }
        return points;
    }

    private List<OsrmRouteClient.NavigationInstruction> parseInstructions(JSONObject response) throws Exception {
        List<OsrmRouteClient.NavigationInstruction> instructions = new ArrayList<>();
        JSONObject trip = response.optJSONObject("trip");
        JSONArray legs = trip == null ? null : trip.optJSONArray("legs");
        if (legs == null) return instructions;
        int instructionIndex = 0;
        for (int legIndex = 0; legIndex < legs.length(); legIndex++) {
            JSONArray maneuvers = legs.getJSONObject(legIndex).optJSONArray("maneuvers");
            if (maneuvers == null) continue;
            for (int maneuverIndex = 0; maneuverIndex < maneuvers.length(); maneuverIndex++) {
                JSONObject maneuver = maneuvers.getJSONObject(maneuverIndex);
                instructions.add(new OsrmRouteClient.NavigationInstruction(
                        instructionIndex++,
                        maneuver.optString("type", "continue"),
                        "",
                        maneuver.optString("street_names", ""),
                        maneuver.optDouble("length", 0.0) * 1000.0,
                        maneuver.optDouble("time", 0.0),
                        maneuver.optDouble("begin_lat", 0.0),
                        maneuver.optDouble("begin_lon", 0.0),
                        maneuver.optString("instruction", "Đi theo tuyến đường")));
            }
        }
        return instructions;
    }

    private double parseDistanceMeters(JSONObject response) {
        JSONObject trip = response.optJSONObject("trip");
        JSONObject summary = trip == null ? null : trip.optJSONObject("summary");
        return summary == null ? 0.0 : summary.optDouble("length", 0.0) * 1000.0;
    }

    private double parseDurationSeconds(JSONObject response) {
        JSONObject trip = response.optJSONObject("trip");
        JSONObject summary = trip == null ? null : trip.optJSONObject("summary");
        return summary == null ? 0.0 : summary.optDouble("time", 0.0);
    }

    private RoadRoute fallbackRoadRoute(List<GeoPoint> points, String warning) {
        RouteQuality quality = new RouteQuality("valhalla", 0.0, false, true, Collections.singletonList(warning));
        return new RoadRoute("valhalla_unavailable", false, points, Collections.emptyList(), Collections.emptyList(), 0.0, 0.0, quality);
    }

    private String stripTrailingSlash(String value) {
        if (value == null || value.isBlank()) return DEFAULT_BASE_URL;
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
