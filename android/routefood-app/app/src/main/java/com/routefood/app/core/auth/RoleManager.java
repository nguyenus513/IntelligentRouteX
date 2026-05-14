package com.routefood.app.core.auth;

import android.content.Context;
import android.content.Intent;

import com.google.android.gms.tasks.Task;
import com.google.firebase.auth.FirebaseUser;
import com.routefood.app.feature.driver.compose.DriverShellActivity;
import com.routefood.app.feature.driver.DriverMainActivity;
import com.routefood.app.feature.user.UserMainActivity;

public class RoleManager {
    private final SessionStore sessionStore;
    private final AuthManager authManager;
    private final SupabaseProfileClient supabaseProfileClient;

    public RoleManager(Context context) {
        sessionStore = new SessionStore(context);
        authManager = new AuthManager(context);
        supabaseProfileClient = new SupabaseProfileClient();
    }

    public UserRole currentRole() {
        return sessionStore.getDemoRole();
    }

    public void setDemoRole(UserRole role) {
        sessionStore.setDemoRole(role);
    }

    public boolean hasSignedInUser() {
        return authManager.hasSignedInUser();
    }

    public Task<UserRole> resolveRole() {
        FirebaseUser user = authManager.currentUser();
        if (user == null && authManager.currentSupabaseUserId() != null && authManager.currentSupabaseAccessToken() != null) {
            com.google.android.gms.tasks.TaskCompletionSource<UserRole> source = new com.google.android.gms.tasks.TaskCompletionSource<>();
            supabaseProfileClient.fetchRole(authManager.currentSupabaseUserId(), authManager.currentSupabaseAccessToken(), new SupabaseProfileClient.ProfileCallback() {
                @Override
                public void onSuccess(UserRole role) {
                    sessionStore.setDemoRole(role);
                    source.setResult(role);
                }

                @Override
                public void onError(Exception error) {
                    source.setResult(sessionStore.getDemoRole());
                }
            });
            return source.getTask();
        }
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
            return new Intent(context, DriverShellActivity.class);
        }
        return new Intent(context, UserMainActivity.class);
    }

    public Intent homeIntent(Context context, UserRole role) {
        if (role == UserRole.DRIVER) {
            return new Intent(context, DriverShellActivity.class);
        }
        return new Intent(context, UserMainActivity.class);
    }
}
