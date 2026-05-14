package com.routefood.app.core.auth;

import android.os.Handler;
import android.os.Looper;

import com.routefood.app.core.supabase.SupabaseConfig;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.OutputStreamWriter;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SupabaseAuthClient {
    public interface AuthCallback {
        void onSuccess(SupabaseAuthSession session);
        void onError(Exception error);
    }

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public boolean isConfigured() {
        return SupabaseConfig.isConfigured();
    }

    public void signIn(String email, String password, AuthCallback callback) {
        postAuth("/auth/v1/token?grant_type=password", email, password, callback);
    }

    public void signUp(String email, String password, AuthCallback callback) {
        postAuth("/auth/v1/signup", email, password, callback);
    }

    public void refreshSession(String refreshToken, AuthCallback callback) {
        if (!isConfigured()) {
            callback.onError(new IllegalStateException("Supabase Auth is not configured."));
            return;
        }
        executor.execute(() -> {
            try {
                JSONObject payload = new JSONObject().put("refresh_token", refreshToken);
                JSONObject json = post("/auth/v1/token?grant_type=refresh_token", payload);
                SupabaseAuthSession session = SupabaseAuthSession.fromJson(json, "");
                mainHandler.post(() -> callback.onSuccess(session));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    private void postAuth(String path, String email, String password, AuthCallback callback) {
        if (!isConfigured()) {
            callback.onError(new IllegalStateException("Supabase Auth is not configured."));
            return;
        }
        executor.execute(() -> {
            try {
                JSONObject payload = new JSONObject()
                        .put("email", email)
                        .put("password", password);
                JSONObject json = post(path, payload);
                SupabaseAuthSession session = SupabaseAuthSession.fromJson(json, email);
                mainHandler.post(() -> callback.onSuccess(session));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    private JSONObject post(String path, JSONObject payload) throws Exception {
        URL url = new URL(SupabaseConfig.url().replaceAll("/$", "") + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(8000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("apikey", SupabaseConfig.publishableKey());
        connection.setRequestProperty("Authorization", "Bearer " + SupabaseConfig.publishableKey());
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("Accept", "application/json");
        try (OutputStreamWriter writer = new OutputStreamWriter(connection.getOutputStream(), StandardCharsets.UTF_8)) {
            writer.write(payload.toString());
        }
        int code = connection.getResponseCode();
        String body = readBody(connection, code);
        if (code < 200 || code >= 300) {
            String message = body;
            try {
                JSONObject error = new JSONObject(body);
                message = error.optString("msg", error.optString("message", body));
            } catch (Exception ignored) {
            }
            throw new IllegalStateException(message);
        }
        return new JSONObject(body);
    }

    private String readBody(HttpURLConnection connection, int code) throws Exception {
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new java.io.InputStreamReader(
                code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream(),
                StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        }
        return body.toString();
    }
}
