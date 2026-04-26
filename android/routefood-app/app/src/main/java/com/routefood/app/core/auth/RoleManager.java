package com.routefood.app.core.auth;

import android.content.Context;
import android.content.Intent;

import com.google.android.gms.tasks.Task;
import com.google.firebase.auth.FirebaseUser;
import com.routefood.app.feature.driver.DriverMainActivity;
import com.routefood.app.feature.user.UserMainActivity;

public class RoleManager {
    private final SessionStore sessionStore;
    private final AuthManager authManager;

    public RoleManager(Context context) {
        sessionStore = new SessionStore(context);
        authManager = new AuthManager(context);
    }

    public UserRole currentRole() {
        return sessionStore.getDemoRole();
    }

    public void setDemoRole(UserRole role) {
        sessionStore.setDemoRole(role);
    }

    public boolean hasSignedInUser() {
        return authManager.currentUser() != null;
    }

    public Task<UserRole> resolveRole() {
        FirebaseUser user = authManager.currentUser();
        if (user == null) {
            return com.google.android.gms.tasks.Tasks.forResult(sessionStore.getDemoRole());
        }
        return user.getIdToken(true).continueWith(task -> {
            if (!task.isSuccessful() || task.getResult() == null) {
                return sessionStore.getDemoRole();
            }
            Object role = task.getResult().getClaims().get("role");
            if (role instanceof String) {
                return UserRole.fromWireName((String) role);
            }
            return sessionStore.getDemoRole();
        });
    }

    public Intent homeIntent(Context context) {
        if (currentRole() == UserRole.DRIVER) {
            return new Intent(context, DriverMainActivity.class);
        }
        return new Intent(context, UserMainActivity.class);
    }

    public Intent homeIntent(Context context, UserRole role) {
        if (role == UserRole.DRIVER) {
            return new Intent(context, DriverMainActivity.class);
        }
        return new Intent(context, UserMainActivity.class);
    }
}
