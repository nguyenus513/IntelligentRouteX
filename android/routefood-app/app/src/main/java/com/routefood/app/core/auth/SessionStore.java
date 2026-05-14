package com.routefood.app.core.auth;

import android.content.Context;
import android.content.SharedPreferences;

public class SessionStore {
    private static final String PREFS_NAME = "routefood_session";
    private static final String KEY_DEMO_ROLE = "demo_role";
    private static final String KEY_ACCESS_TOKEN = "supabase_access_token";
    private static final String KEY_REFRESH_TOKEN = "supabase_refresh_token";
    private static final String KEY_USER_ID = "supabase_user_id";
    private static final String KEY_EMAIL = "supabase_email";

    private final SharedPreferences preferences;

    public SessionStore(Context context) {
        preferences = context.getApplicationContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public UserRole getDemoRole() {
        return UserRole.fromWireName(preferences.getString(KEY_DEMO_ROLE, UserRole.USER.wireName()));
    }

    public void setDemoRole(UserRole role) {
        preferences.edit().putString(KEY_DEMO_ROLE, role.wireName()).apply();
    }

    public void saveSupabaseSession(String userId, String email, String accessToken, String refreshToken, UserRole role) {
        preferences.edit()
                .putString(KEY_USER_ID, userId)
                .putString(KEY_EMAIL, email)
                .putString(KEY_ACCESS_TOKEN, accessToken)
                .putString(KEY_REFRESH_TOKEN, refreshToken)
                .putString(KEY_DEMO_ROLE, role.wireName())
                .apply();
    }

    public boolean hasSupabaseSession() {
        return getSupabaseAccessToken() != null && getSupabaseUserId() != null;
    }

    public String getSupabaseAccessToken() {
        return preferences.getString(KEY_ACCESS_TOKEN, null);
    }

    public String getSupabaseRefreshToken() {
        return preferences.getString(KEY_REFRESH_TOKEN, null);
    }

    public String getSupabaseUserId() {
        return preferences.getString(KEY_USER_ID, null);
    }

    public String getSupabaseEmail() {
        return preferences.getString(KEY_EMAIL, null);
    }

    public void clearSupabaseSession() {
        preferences.edit()
                .remove(KEY_ACCESS_TOKEN)
                .remove(KEY_REFRESH_TOKEN)
                .remove(KEY_USER_ID)
                .remove(KEY_EMAIL)
                .apply();
    }
}
