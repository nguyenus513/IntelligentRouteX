package com.routefood.app.core.map;

import android.os.Handler;
import android.os.Looper;

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
    public interface Callback {
        void onRoute(List<GeoPoint> routePoints);

        void onError(Exception error);
    }

    private static final String BASE_URL = "https://router.project-osrm.org/route/v1/driving/";
    private final ExecutorService executorService = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public void route(GeoPoint driver, GeoPoint pickup, GeoPoint dropoff, Callback callback) {
        executorService.execute(() -> {
            try {
                String coordinates = coordinate(driver) + ";" + coordinate(pickup) + ";" + coordinate(dropoff);
                URL url = new URL(BASE_URL + coordinates + "?overview=full&geometries=geojson&steps=false");
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

    private String coordinate(GeoPoint point) {
        return String.format(Locale.US, "%.6f,%.6f", point.longitude(), point.latitude());
    }
}
