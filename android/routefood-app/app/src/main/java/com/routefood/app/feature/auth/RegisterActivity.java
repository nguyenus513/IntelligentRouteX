package com.routefood.app.feature.auth;

import android.os.Bundle;
import android.content.Intent;
import android.widget.Toast;

import com.google.android.material.textfield.TextInputEditText;
import com.routefood.app.R;
import com.routefood.app.core.auth.AuthManager;
import com.routefood.app.core.ui.BaseActivity;

public class RegisterActivity extends BaseActivity {
    private AuthManager authManager;
    private TextInputEditText emailInput;
    private TextInputEditText passwordInput;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_register);
        authManager = new AuthManager(this);
        emailInput = findViewById(R.id.registerEmailInput);
        passwordInput = findViewById(R.id.registerPasswordInput);

        findViewById(R.id.createAccountButton).setOnClickListener(view -> register());
        findViewById(R.id.backToLoginButton).setOnClickListener(view -> finish());
    }

    private void register() {
        String email = textOf(emailInput);
        String password = textOf(passwordInput);
        if (!authManager.isFirebaseAvailable()) {
            Toast.makeText(this, "Firebase config missing; continuing in local demo mode.", Toast.LENGTH_SHORT).show();
            startActivity(new Intent(this, SelectRoleActivity.class));
            return;
        }
        if (email.isEmpty() || password.length() < 6) {
            Toast.makeText(this, "Enter email and a 6+ character password.", Toast.LENGTH_SHORT).show();
            return;
        }
        authManager.register(email, password)
                .addOnSuccessListener(result -> startActivity(new Intent(this, SelectRoleActivity.class)))
                .addOnFailureListener(error -> Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show());
    }

    private String textOf(TextInputEditText input) {
        return input.getText() == null ? "" : input.getText().toString().trim();
    }
}
