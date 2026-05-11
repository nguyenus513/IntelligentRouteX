package com.routefood.app.core.map;

import android.os.Handler;
import android.os.Looper;

import com.routefood.app.BuildConfig;
import com.routefood.app.data.model.GeoPoint;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class OsrmRouteClient {
    public static class NavigationInstruction {
        public final int index;
        public final String type;
        public final String modifier;
        public final String roadName;
        public final double distanceMeters;
        public final double durationSeconds;
        public final double latitude;
        public final double longitude;
        public final String text;

        public NavigationInstruction(int index, String type, String modifier, String roadName, double distanceMeters, double durationSeconds, double latitude, double longitude, String text) {
            this.index = index;
            this.type = type;
            this.modifier = modifier;
            this.roadName = roadName;
            this.distanceMeters = distanceMeters;
            this.durationSeconds = durationSeconds;
            this.latitude = latitude;
            this.longitude = longitude;
            this.text = text;
        }
    }

    public static class NavigationRouteResult {
        public final List<GeoPoint> geometry;
        public final List<NavigationInstruction> instructions;
        public final List<SnappedWaypoint> waypoints;
        public final double distanceMeters;
        public final double durationSeconds;
        public final double maxSnapDistanceMeters;
        public final List<Double> legDistanceMeters;

        public NavigationRouteResult(List<GeoPoint> geometry, List<NavigationInstruction> instructions, double distanceMeters, double durationSeconds) {
            this(geometry, instructions, new ArrayList<>(), distanceMeters, durationSeconds, 0.0, new ArrayList<>());
        }

        public NavigationRouteResult(List<GeoPoint> geometry, List<NavigationInstruction> instructions, List<SnappedWaypoint> waypoints, double distanceMeters, double durationSeconds, double maxSnapDistanceMeters) {
            this(geometry, instructions, waypoints, distanceMeters, durationSeconds, maxSnapDistanceMeters, new ArrayList<>());
        }

        public NavigationRouteResult(List<GeoPoint> geometry, List<NavigationInstruction> instructions, List<SnappedWaypoint> waypoints, double distanceMeters, double durationSeconds, double maxSnapDistanceMeters, List<Double> legDistanceMeters) {
            this.geometry = geometry;
            this.instructions = instructions;
            this.waypoints = waypoints;
            this.distanceMeters = distanceMeters;
            this.durationSeconds = durationSeconds;
            this.maxSnapDistanceMeters = maxSnapDistanceMeters;
            this.legDistanceMeters = legDistanceMeters;
        }
    }

    public static class SnappedWaypoint {
        public final int index;
        public final GeoPoint raw;
        public final GeoPoint snapped;
        public final double distanceMeters;
        public final String roadName;

        public SnappedWaypoint(int index, GeoPoint raw, GeoPoint snapped, double distanceMeters, String roadName) {
            this.index = index;
            this.raw = raw;
            this.snapped = snapped;
            this.distanceMeters = distanceMeters;
            this.roadName = roadName;
        }
    }

    public interface Callback {
        void onRoute(List<GeoPoint> routePoints);

        void onError(Exception error);
    }

    private final String routeUrl;
    private final String nearestUrl;
    private static final double MAX_SNAP_DISTANCE_METERS = 150.0;
    private final ExecutorService executorService = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public OsrmRouteClient() {
        this(BuildConfig.OSRM_BASE_URL);
    }

    public OsrmRouteClient(String baseUrl) {
        String safeBaseUrl = stripTrailingSlash(baseUrl == null || baseUrl.isBlank() ? BuildConfig.PUBLIC_OSRM_BASE_URL : baseUrl);
        this.routeUrl = safeBaseUrl + "/route/v1/driving/";
        this.nearestUrl = safeBaseUrl + "/nearest/v1/driving/";
    }

    public void route(GeoPoint driver, GeoPoint pickup, GeoPoint dropoff, Callback callback) {
        executorService.execute(() -> {
            try {
                String coordinates = coordinate(driver) + ";" + coordinate(pickup) + ";" + coordinate(dropoff);
                URL url = new URL(routeUrl + coordinates + "?overview=full&geometries=geojson&steps=false");
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);
                connection.setRequestMethod("GET");

                int responseCode = connection.getResponseCode();
                if (responseCode < 200 || responseCode >= 300) {
                    throw new IllegalStateException("OSRM route failed with HTTP " + responseCode);
                }

                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        body.append(line);
                    }
                }

                List<GeoPoint> points = parseRoute(body.toString());
                mainHandler.post(() -> callback.onRoute(points));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    public void routeLeg(GeoPoint from, GeoPoint to, Callback callback) {
        executorService.execute(() -> {
            try {
                String coordinates = coordinate(from) + ";" + coordinate(to);
                URL url = new URL(routeUrl + coordinates + "?overview=full&geometries=geojson&steps=false");
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);
                connection.setRequestMethod("GET");
                int responseCode = connection.getResponseCode();
                if (responseCode < 200 || responseCode >= 300) {
                    throw new IllegalStateException("OSRM leg failed with HTTP " + responseCode);
                }
                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        body.append(line);
                    }
                }
                List<GeoPoint> points = parseRoute(body.toString());
                mainHandler.post(() -> callback.onRoute(points));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    public void routeWaypoints(List<GeoPoint> waypoints, Callback callback) {
        if (waypoints == null || waypoints.size() < 2) {
            mainHandler.post(() -> callback.onRoute(waypoints == null ? new ArrayList<>() : new ArrayList<>(waypoints)));
            return;
        }
        executorService.execute(() -> {
            try {
                StringBuilder coordinates = new StringBuilder();
                for (int index = 0; index < waypoints.size(); index++) {
                    if (index > 0) coordinates.append(';');
                    coordinates.append(coordinate(waypoints.get(index)));
                }
                URL url = new URL(routeUrl + coordinates + "?overview=full&geometries=geojson&steps=false");
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setConnectTimeout(6000);
                connection.setReadTimeout(6000);
                connection.setRequestMethod("GET");
                int responseCode = connection.getResponseCode();
                if (responseCode < 200 || responseCode >= 300) {
                    throw new IllegalStateException("OSRM route failed with HTTP " + responseCode);
                }
                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        body.append(line);
                    }
                }
                List<GeoPoint> points = parseRoute(body.toString());
                mainHandler.post(() -> callback.onRoute(points));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    public List<GeoPoint> routeWaypointsBlocking(List<GeoPoint> waypoints) throws Exception {
        if (waypoints == null || waypoints.size() < 2) {
            return waypoints == null ? new ArrayList<>() : new ArrayList<>(waypoints);
        }
        StringBuilder coordinates = new StringBuilder();
        for (int index = 0; index < waypoints.size(); index++) {
            if (index > 0) coordinates.append(';');
            coordinates.append(coordinate(waypoints.get(index)));
        }
        URL url = new URL(routeUrl + coordinates + "?overview=full&geometries=geojson&steps=false");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(7000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("User-Agent", "RouteFoodDemo/0.1 Android IntelligentRouteX");
        int responseCode = connection.getResponseCode();
        if (responseCode < 200 || responseCode >= 300) {
            throw new IllegalStateException("OSRM route failed with HTTP " + responseCode);
        }
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        }
        return parseRoute(body.toString());
    }

    public NavigationRouteResult routeWaypointsNavigationBlocking(List<GeoPoint> waypoints) throws Exception {
        if (waypoints == null || waypoints.size() < 2) {
            List<GeoPoint> safe = waypoints == null ? new ArrayList<>() : new ArrayList<>(waypoints);
            return new NavigationRouteResult(safe, new ArrayList<>(), 0.0, 0.0);
        }
        List<SnappedWaypoint> snappedWaypoints = snapWaypointsBlocking(waypoints);
        double maxSnapDistance = 0.0;
        StringBuilder coordinates = new StringBuilder();
        for (int index = 0; index < snappedWaypoints.size(); index++) {
            if (index > 0) coordinates.append(';');
            SnappedWaypoint waypoint = snappedWaypoints.get(index);
            maxSnapDistance = Math.max(maxSnapDistance, waypoint.distanceMeters);
            if (waypoint.distanceMeters > MAX_SNAP_DISTANCE_METERS) {
                throw new IllegalStateException("OSRM waypoint snap too far at index " + index + ": " + waypoint.distanceMeters + "m");
            }
            coordinates.append(coordinate(waypoint.snapped));
        }
        URL url = new URL(routeUrl + coordinates + "?overview=full&geometries=geojson&steps=true&annotations=true");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(7000);
        connection.setReadTimeout(7000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("User-Agent", "RouteFoodDemo/0.1 Android IntelligentRouteX");
        int responseCode = connection.getResponseCode();
        if (responseCode < 200 || responseCode >= 300) {
            throw new IllegalStateException("OSRM navigation route failed with HTTP " + responseCode);
        }
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        }
        return parseNavigationRoute(body.toString(), snappedWaypoints, maxSnapDistance);
    }

    private List<SnappedWaypoint> snapWaypointsBlocking(List<GeoPoint> rawWaypoints) throws Exception {
        List<SnappedWaypoint> snapped = new ArrayList<>();
        for (int index = 0; index < rawWaypoints.size(); index++) {
            snapped.add(snapWaypointBlocking(index, rawWaypoints.get(index)));
        }
        return snapped;
    }

    private SnappedWaypoint snapWaypointBlocking(int index, GeoPoint raw) throws Exception {
        URL url = new URL(nearestUrl + coordinate(raw) + "?number=1");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("User-Agent", "RouteFoodDemo/0.1 Android IntelligentRouteX");
        int responseCode = connection.getResponseCode();
        if (responseCode < 200 || responseCode >= 300) {
            throw new IllegalStateException("OSRM nearest failed with HTTP " + responseCode);
        }
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        }
        JSONObject root = new JSONObject(body.toString());
        if (!"Ok".equals(root.optString("code"))) {
            throw new IllegalStateException("OSRM nearest response code: " + root.optString("code"));
        }
        JSONArray waypoints = root.optJSONArray("waypoints");
        if (waypoints == null || waypoints.length() == 0) {
            throw new IllegalStateException("OSRM nearest returned no waypoint.");
        }
        JSONObject waypoint = waypoints.getJSONObject(0);
        JSONArray location = waypoint.getJSONArray("location");
        GeoPoint snapped = new GeoPoint(location.getDouble(1), location.getDouble(0));
        return new SnappedWaypoint(index, raw, snapped, waypoint.optDouble("distance", 0.0), waypoint.optString("name", ""));
    }

    private List<GeoPoint> parseRoute(String body) throws Exception {
        JSONObject root = new JSONObject(body);
        if (!"Ok".equals(root.optString("code"))) {
            throw new IllegalStateException("OSRM response code: " + root.optString("code"));
        }
        JSONArray routes = root.getJSONArray("routes");
        if (routes.length() == 0) {
            throw new IllegalStateException("OSRM returned no routes.");
        }
        JSONArray coordinates = routes.getJSONObject(0)
                .getJSONObject("geometry")
                .getJSONArray("coordinates");
        List<GeoPoint> points = new ArrayList<>();
        for (int index = 0; index < coordinates.length(); index++) {
            JSONArray coordinate = coordinates.getJSONArray(index);
            points.add(new GeoPoint(coordinate.getDouble(1), coordinate.getDouble(0)));
        }
        return points;
    }

    private NavigationRouteResult parseNavigationRoute(String body, List<SnappedWaypoint> waypoints, double maxSnapDistanceMeters) throws Exception {
        JSONObject root = new JSONObject(body);
        if (!"Ok".equals(root.optString("code"))) {
            throw new IllegalStateException("OSRM response code: " + root.optString("code"));
        }
        JSONArray routes = root.getJSONArray("routes");
        if (routes.length() == 0) {
            throw new IllegalStateException("OSRM returned no routes.");
        }
        JSONObject route = routes.getJSONObject(0);
        List<GeoPoint> geometry = parseRoute(body);
        List<NavigationInstruction> instructions = new ArrayList<>();
        List<Double> legDistanceMeters = new ArrayList<>();
        JSONArray legs = route.optJSONArray("legs");
        int instructionIndex = 0;
        if (legs != null) {
            for (int legIndex = 0; legIndex < legs.length(); legIndex++) {
                JSONObject leg = legs.getJSONObject(legIndex);
                legDistanceMeters.add(leg.optDouble("distance", 0.0));
                JSONArray steps = leg.optJSONArray("steps");
                if (steps == null) continue;
                for (int stepIndex = 0; stepIndex < steps.length(); stepIndex++) {
                    JSONObject step = steps.getJSONObject(stepIndex);
                    JSONObject maneuver = step.optJSONObject("maneuver");
                    JSONArray location = maneuver == null ? null : maneuver.optJSONArray("location");
                    double longitude = location != null && location.length() >= 2 ? location.optDouble(0) : 0.0;
                    double latitude = location != null && location.length() >= 2 ? location.optDouble(1) : 0.0;
                    String type = maneuver == null ? "continue" : maneuver.optString("type", "continue");
                    String modifier = maneuver == null ? "" : maneuver.optString("modifier", "");
                    String roadName = step.optString("name", "");
                    instructions.add(new NavigationInstruction(
                            instructionIndex++,
                            type,
                            modifier,
                            roadName,
                            step.optDouble("distance", 0.0),
                            step.optDouble("duration", 0.0),
                            latitude,
                            longitude,
                            instructionText(type, modifier, roadName)));
                }
            }
        }
        return new NavigationRouteResult(geometry, instructions, waypoints, route.optDouble("distance", 0.0), route.optDouble("duration", 0.0), maxSnapDistanceMeters, legDistanceMeters);
    }

    private String instructionText(String type, String modifier, String roadName) {
        String road = roadName == null || roadName.isBlank() ? "đường phía trước" : roadName;
        if ("arrive".equals(type)) return "Đến điểm dừng";
        if ("depart".equals(type)) return "Bắt đầu đi theo " + road;
        if ("roundabout".equals(type) || "rotary".equals(type)) return "Vào vòng xoay rồi ra theo " + road;
        if ("merge".equals(type)) return "Nhập làn vào " + road;
        if ("fork".equals(type)) return "Đi theo nhánh " + road;
        if ("turn".equals(type) || "end of road".equals(type) || "new name".equals(type)) {
            if ("right".equals(modifier) || "slight right".equals(modifier) || "sharp right".equals(modifier)) return "Rẽ phải vào " + road;
            if ("left".equals(modifier) || "slight left".equals(modifier) || "sharp left".equals(modifier)) return "Rẽ trái vào " + road;
            if ("uturn".equals(modifier)) return "Quay đầu khi có thể";
        }
        return "Đi thẳng theo " + road;
    }

    private String coordinate(GeoPoint point) {
        return String.format(Locale.US, "%.6f,%.6f", point.longitude(), point.latitude());
    }

    private String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
