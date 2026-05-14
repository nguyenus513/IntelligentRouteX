package com.routefood.app.core.supabase;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SupabaseRestClient {
    public interface JsonArrayCallback {
        void onSuccess(JSONArray array);

        void onError(Exception error);
    }

    private final ExecutorService executorService = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public boolean isConfigured() {
        return SupabaseConfig.isConfigured();
    }

    public void select(String table, Map<String, String> query, JsonArrayCallback callback) {
        select(table, query, null, callback);
    }

    public void select(String table, Map<String, String> query, String accessToken, JsonArrayCallback callback) {
        if (!isConfigured()) {
            callback.onError(new IllegalStateException("Supabase publishable key is not configured."));
            return;
        }
        executorService.execute(() -> {
            try {
                URL url = new URL(SupabaseConfig.url().replaceAll("/$", "") + "/rest/v1/" + table + queryString(query));
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setConnectTimeout(6000);
                connection.setReadTimeout(6000);
                connection.setRequestMethod("GET");
                connection.setRequestProperty("apikey", SupabaseConfig.publishableKey());
                connection.setRequestProperty("Authorization", "Bearer " + (accessToken == null ? SupabaseConfig.publishableKey() : accessToken));
                connection.setRequestProperty("Accept", "application/json");
                int code = connection.getResponseCode();
                if (code < 200 || code >= 300) {
                    throw new IllegalStateException("Supabase GET " + table + " failed with HTTP " + code);
                }
                StringBuilder body = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        body.append(line);
                    }
                }
                JSONArray array = new JSONArray(body.toString());
                mainHandler.post(() -> callback.onSuccess(array));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    public static Map<String, String> query() {
        return new LinkedHashMap<>();
    }

    private String queryString(Map<String, String> query) throws Exception {
        if (query == null || query.isEmpty()) {
            return "";
        }
        StringBuilder builder = new StringBuilder("?");
        boolean first = true;
        for (Map.Entry<String, String> entry : query.entrySet()) {
            if (!first) {
                builder.append('&');
            }
            first = false;
            builder.append(encode(entry.getKey())).append('=').append(encode(entry.getValue()));
        }
        return builder.toString();
    }

    private String encode(String value) throws Exception {
        return URLEncoder.encode(value, StandardCharsets.UTF_8.name()).replace("+", "%20");
    }
}
