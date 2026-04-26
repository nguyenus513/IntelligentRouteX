package com.routefood.app.feature.auth;

import android.os.Bundle;
import android.widget.Toast;

import com.routefood.app.R;
import com.routefood.app.core.auth.AuthManager;
import com.routefood.app.core.auth.RoleManager;
import com.routefood.app.core.auth.UserRole;
import com.routefood.app.core.firebase.FunctionsClient;
import com.routefood.app.core.ui.BaseActivity;

public class SelectRoleActivity extends BaseActivity {
    private RoleManager roleManager;
    private AuthManager authManager;
    private FunctionsClient functionsClient;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_select_role);
        roleManager = new RoleManager(this);
        authManager = new AuthManager(this);
        functionsClient = new FunctionsClient(this);

        findViewById(R.id.userCard).setOnClickListener(view -> openHome(UserRole.USER));
        findViewById(R.id.driverCard).setOnClickListener(view -> openHome(UserRole.DRIVER));
    }

    private void openHome(UserRole role) {
        roleManager.setDemoRole(role);
        if (!authManager.isFirebaseAvailable() || authManager.currentUser() == null) {
            startRoleHome(role);
            return;
        }
        functionsClient.bootstrapDemoRole(role.wireName())
                .addOnSuccessListener(result -> startRoleHome(role))
                .addOnFailureListener(error -> Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show());
    }

    private void startRoleHome(UserRole role) {
        startActivity(roleManager.homeIntent(this, role));
        finishAffinity();
    }
}
