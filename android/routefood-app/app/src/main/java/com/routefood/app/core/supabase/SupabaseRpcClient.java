package com.routefood.app.core.supabase;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.OutputStreamWriter;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class SupabaseRpcClient {
    public JSONObject call(String functionName, JSONObject payload, String accessToken) throws Exception {
        URL url = new URL(SupabaseConfig.url().replaceAll("/$", "") + "/rest/v1/rpc/" + functionName);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(9000);
        connection.setReadTimeout(9000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("apikey", SupabaseConfig.publishableKey());
        connection.setRequestProperty("Authorization", "Bearer " + accessToken);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("Accept", "application/json");
        try (OutputStreamWriter writer = new OutputStreamWriter(connection.getOutputStream(), StandardCharsets.UTF_8)) {
            writer.write(payload.toString());
        }
        int code = connection.getResponseCode();
        String body = readBody(connection, code);
        if (code < 200 || code >= 300) throw new IllegalStateException(body);
        return new JSONObject(body);
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
}
