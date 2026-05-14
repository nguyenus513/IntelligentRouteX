package com.routefood.app.feature.auth;

import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

import com.google.android.material.textfield.TextInputEditText;
import com.routefood.app.R;
import com.routefood.app.core.auth.AuthManager;
import com.routefood.app.core.auth.SessionStore;
import com.routefood.app.core.auth.SupabaseAuthClient;
import com.routefood.app.core.auth.SupabaseAuthSession;
import com.routefood.app.core.auth.SupabaseProfileClient;
import com.routefood.app.core.ui.BaseActivity;

public class LoginActivity extends BaseActivity {
    private AuthManager authManager;
    private SupabaseAuthClient supabaseAuthClient;
    private SupabaseProfileClient supabaseProfileClient;
    private SessionStore sessionStore;
    private TextInputEditText emailInput;
    private TextInputEditText passwordInput;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);
        authManager = new AuthManager(this);
        supabaseAuthClient = new SupabaseAuthClient();
        supabaseProfileClient = new SupabaseProfileClient();
        sessionStore = new SessionStore(this);
        emailInput = findViewById(R.id.emailInput);
        passwordInput = findViewById(R.id.passwordInput);

        findViewById(R.id.loginButton).setOnClickListener(view -> login());
        findViewById(R.id.registerButton).setOnClickListener(view ->
                startActivity(new Intent(this, RegisterActivity.class)));
    }

    private void login() {
        String email = textOf(emailInput);
        String password = textOf(passwordInput);
        if (email.toLowerCase(java.util.Locale.US).contains("demo")) {
            startDemoMode("Using Firebase demo data.");
            return;
        }
        if (email.isEmpty() || password.length() < 6) {
            Toast.makeText(this, "Enter email and a 6+ character password.", Toast.LENGTH_SHORT).show();
            return;
        }
        if (supabaseAuthClient.isConfigured()) {
            supabaseAuthClient.signIn(email, password, new SupabaseAuthClient.AuthCallback() {
                @Override
                public void onSuccess(SupabaseAuthSession session) {
                    supabaseProfileClient.fetchRole(session.userId(), session.accessToken(), new SupabaseProfileClient.ProfileCallback() {
                        @Override
                        public void onSuccess(com.routefood.app.core.auth.UserRole role) {
                            sessionStore.saveSupabaseSession(session.userId(), session.email(), session.accessToken(), session.refreshToken(), role);
                            startActivity(new Intent(LoginActivity.this, SelectRoleActivity.class));
                        }

                        @Override
                        public void onError(Exception error) {
                            sessionStore.saveSupabaseSession(session.userId(), session.email(), session.accessToken(), session.refreshToken(), sessionStore.getDemoRole());
                            startActivity(new Intent(LoginActivity.this, SelectRoleActivity.class));
                        }
                    });
                }

                @Override
                public void onError(Exception error) {
                    handleAuthFailure(error);
                }
            });
            return;
        }
        if (!authManager.isFirebaseAvailable()) {
            startDemoMode("Supabase/Firebase config missing; using local demo mode.");
            return;
        }
        authManager.signIn(email, password)
                .addOnSuccessListener(result -> startActivity(new Intent(this, SelectRoleActivity.class)))
                .addOnFailureListener(this::handleAuthFailure);
    }

    private void handleAuthFailure(Exception error) {
        String message = error.getMessage() == null ? "" : error.getMessage();
        if (message.contains("CONFIGURATION_NOT_FOUND")) {
            startDemoMode("Firebase Auth is not enabled; using Firebase demo data.");
            return;
        }
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private void startDemoMode(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
        startActivity(new Intent(this, SelectRoleActivity.class));
    }

    private String textOf(TextInputEditText input) {
        return input.getText() == null ? "" : input.getText().toString().trim();
    }
}
