package com.routefood.app.core.map.routing;

import com.routefood.app.BuildConfig;
import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.data.model.GeoPoint;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class GraphHopperRoutingProvider implements RoutingProvider {
    private final String baseUrl;
    private final String apiKey;
    private final String profile;

    public GraphHopperRoutingProvider() {
        this(BuildConfig.GRAPHHOPPER_BASE_URL, BuildConfig.GRAPHHOPPER_API_KEY, BuildConfig.GRAPHHOPPER_PROFILE);
    }

    public GraphHopperRoutingProvider(String baseUrl, String apiKey, String profile) {
        this.baseUrl = stripTrailingSlash(baseUrl == null || baseUrl.isBlank() ? "https://graphhopper.com/api/1" : baseUrl);
        this.apiKey = apiKey == null ? "" : apiKey;
        this.profile = profile == null || profile.isBlank() ? "car" : profile;
    }

    @Override
    public RoadRoute routeFixedOrder(List<GeoPoint> rawWaypoints) throws Exception {
        if (apiKey.isBlank()) {
            throw new IllegalStateException("GraphHopper API key is not configured.");
        }
        JSONObject response = requestRoute(rawWaypoints);
        JSONArray paths = response.optJSONArray("paths");
        if (paths == null || paths.length() == 0) {
            throw new IllegalStateException("GraphHopper returned no paths.");
        }
        JSONObject path = paths.getJSONObject(0);
        List<GeoPoint> coordinates = parseCoordinates(path);
        List<OsrmRouteClient.NavigationInstruction> instructions = parseInstructions(path);
        RouteQuality quality = new RouteQuality("graphhopper", 0.0, coordinates.size() >= 2, true, Collections.emptyList());
        return new RoadRoute(
                "graphhopper_cloud_" + profile + "_v2",
                coordinates.size() >= 2,
                coordinates,
                instructions,
                Collections.emptyList(),
                path.optDouble("distance", 0.0),
                path.optDouble("time", 0.0) / 1000.0,
                quality
        );
    }

    private JSONObject requestRoute(List<GeoPoint> rawWaypoints) throws Exception {
        StringBuilder urlBuilder = new StringBuilder(baseUrl).append("/route?");
        for (GeoPoint waypoint : rawWaypoints) {
            urlBuilder.append("point=")
                    .append(URLEncoder.encode(String.format(Locale.US, "%.6f,%.6f", waypoint.latitude(), waypoint.longitude()), StandardCharsets.UTF_8.name()))
                    .append('&');
        }
        urlBuilder.append("profile=").append(URLEncoder.encode(profile, StandardCharsets.UTF_8.name()))
                .append("&points_encoded=false")
                .append("&instructions=true")
                .append("&locale=vi")
                .append("&calc_points=true")
                .append("&key=").append(URLEncoder.encode(apiKey, StandardCharsets.UTF_8.name()));
        HttpURLConnection connection = (HttpURLConnection) new URL(urlBuilder.toString()).openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(8000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("User-Agent", "RouteFoodDemo/0.1 Android IntelligentRouteX");
        int responseCode = connection.getResponseCode();
        if (responseCode < 200 || responseCode >= 300) {
            throw new IllegalStateException("GraphHopper route failed with HTTP " + responseCode);
        }
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) body.append(line);
        }
        return new JSONObject(body.toString());
    }

    private List<GeoPoint> parseCoordinates(JSONObject path) throws Exception {
        JSONObject points = path.getJSONObject("points");
        JSONArray coordinates = points.getJSONArray("coordinates");
        List<GeoPoint> route = new ArrayList<>();
        for (int index = 0; index < coordinates.length(); index++) {
            JSONArray coordinate = coordinates.getJSONArray(index);
            route.add(new GeoPoint(coordinate.getDouble(1), coordinate.getDouble(0)));
        }
        return route;
    }

    private List<OsrmRouteClient.NavigationInstruction> parseInstructions(JSONObject path) throws Exception {
        List<OsrmRouteClient.NavigationInstruction> instructions = new ArrayList<>();
        JSONArray rawInstructions = path.optJSONArray("instructions");
        if (rawInstructions == null) return instructions;
        for (int index = 0; index < rawInstructions.length(); index++) {
            JSONObject instruction = rawInstructions.getJSONObject(index);
            instructions.add(new OsrmRouteClient.NavigationInstruction(
                    index,
                    String.valueOf(instruction.optInt("sign", 0)),
                    "",
                    instruction.optString("street_name", ""),
                    instruction.optDouble("distance", 0.0),
                    instruction.optDouble("time", 0.0) / 1000.0,
                    0.0,
                    0.0,
                    instruction.optString("text", "Đi theo tuyến đường")
            ));
        }
        return instructions;
    }

    private String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
