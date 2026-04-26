package com.routefood.app.core.auth;

import android.content.Context;
import android.content.Intent;

import com.routefood.app.feature.driver.DriverMainActivity;
import com.routefood.app.feature.user.UserMainActivity;

public class RoleManager {
    private final SessionStore sessionStore;

    public RoleManager(Context context) {
        sessionStore = new SessionStore(context);
    }

    public UserRole currentRole() {
        return sessionStore.getDemoRole();
    }

    public void setDemoRole(UserRole role) {
        sessionStore.setDemoRole(role);
    }

    public Intent homeIntent(Context context) {
        if (currentRole() == UserRole.DRIVER) {
            return new Intent(context, DriverMainActivity.class);
        }
        return new Intent(context, UserMainActivity.class);
    }
}
