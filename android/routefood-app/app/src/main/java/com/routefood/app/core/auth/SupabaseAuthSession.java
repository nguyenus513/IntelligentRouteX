package com.routefood.app.core.auth;

import org.json.JSONObject;

public class SupabaseAuthSession {
    private final String userId;
    private final String email;
    private final String accessToken;
    private final String refreshToken;

    public SupabaseAuthSession(String userId, String email, String accessToken, String refreshToken) {
        this.userId = userId;
        this.email = email;
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
    }

    public String userId() {
        return userId;
    }

    public String email() {
        return email;
    }

    public String accessToken() {
        return accessToken;
    }

    public String refreshToken() {
        return refreshToken;
    }

    public static SupabaseAuthSession fromJson(JSONObject json, String fallbackEmail) {
        JSONObject user = json.optJSONObject("user");
        String userId = user == null ? "" : user.optString("id", "");
        String email = user == null ? fallbackEmail : user.optString("email", fallbackEmail);
        if (email == null || email.isEmpty()) {
            email = fallbackEmail;
        }
        return new SupabaseAuthSession(
                userId,
                email,
                json.optString("access_token", ""),
                json.optString("refresh_token", "")
        );
    }
}
