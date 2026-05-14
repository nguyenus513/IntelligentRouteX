package com.routefood.app.core.auth;

import android.os.Handler;
import android.os.Looper;

import com.routefood.app.core.supabase.SupabaseConfig;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.OutputStreamWriter;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SupabaseProfileClient {
    public interface ProfileCallback {
        void onSuccess(UserRole role);
        void onError(Exception error);
    }

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public void upsertProfile(SupabaseAuthSession session, UserRole role, ProfileCallback callback) {
        executor.execute(() -> {
            try {
                JSONObject profile = new JSONObject()
                        .put("id", session.userId())
                        .put("role", role.wireName())
                        .put("display_name", displayName(session.email()))
                        .put("metadata", new JSONObject().put("source", "android_supabase_auth"));
                patch("profiles", profile, session.accessToken());
                if (role == UserRole.DRIVER) {
                    JSONObject driver = new JSONObject()
                            .put("id", session.userId())
                            .put("name", displayName(session.email()))
                            .put("vehicle_type", "motorbike")
                            .put("status", "offline")
                            .put("online", false);
                    patch("drivers", driver, session.accessToken());
                } else {
                    JSONObject customer = new JSONObject()
                            .put("id", session.userId())
                            .put("preferences", new JSONObject().put("homeFeed", "production_demo"));
                    patch("customers", customer, session.accessToken());
                }
                mainHandler.post(() -> callback.onSuccess(role));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    public void fetchRole(String userId, String accessToken, ProfileCallback callback) {
        executor.execute(() -> {
            try {
                URL url = new URL(SupabaseConfig.url().replaceAll("/$", "") + "/rest/v1/profiles?select=role&id=eq." + encode(userId) + "&limit=1");
                HttpURLConnection connection = connection(url, "GET", accessToken);
                int code = connection.getResponseCode();
                String body = readBody(connection, code);
                if (code < 200 || code >= 300) throw new IllegalStateException(body);
                JSONArray array = new JSONArray(body);
                UserRole role = array.length() == 0 ? UserRole.USER : UserRole.fromWireName(array.getJSONObject(0).optString("role", "user"));
                mainHandler.post(() -> callback.onSuccess(role));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    private void patch(String table, JSONObject payload, String accessToken) throws Exception {
        URL url = new URL(SupabaseConfig.url().replaceAll("/$", "") + "/rest/v1/" + table + "?on_conflict=id");
        HttpURLConnection connection = connection(url, "POST", accessToken);
        connection.setDoOutput(true);
        connection.setRequestProperty("Prefer", "resolution=merge-duplicates,return=minimal");
        try (OutputStreamWriter writer = new OutputStreamWriter(connection.getOutputStream(), StandardCharsets.UTF_8)) {
            writer.write(payload.toString());
        }
        int code = connection.getResponseCode();
        String body = readBody(connection, code);
        if (code < 200 || code >= 300) throw new IllegalStateException(table + ": " + body);
    }

    private HttpURLConnection connection(URL url, String method, String accessToken) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(8000);
        connection.setRequestMethod(method);
        connection.setRequestProperty("apikey", SupabaseConfig.publishableKey());
        connection.setRequestProperty("Authorization", "Bearer " + accessToken);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("Accept", "application/json");
        return connection;
    }

    private String readBody(HttpURLConnection connection, int code) throws Exception {
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new java.io.InputStreamReader(
                code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream(),
                StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) body.append(line);
        }
        return body.toString();
    }

    private String displayName(String email) {
        int at = email == null ? -1 : email.indexOf('@');
        return at > 0 ? email.substring(0, at) : "RouteFood User";
    }

    private String encode(String value) throws Exception {
        return URLEncoder.encode(value, StandardCharsets.UTF_8.name()).replace("+", "%20");
    }
}
