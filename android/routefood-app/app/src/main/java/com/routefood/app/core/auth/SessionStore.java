package com.routefood.app.core.auth;

import android.content.Context;
import android.content.SharedPreferences;

public class SessionStore {
    private static final String PREFS_NAME = "routefood_session";
    private static final String KEY_DEMO_ROLE = "demo_role";

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
}
