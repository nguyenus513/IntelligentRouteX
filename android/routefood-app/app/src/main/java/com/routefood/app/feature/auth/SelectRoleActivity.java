package com.routefood.app.feature.auth;

import android.os.Bundle;

import com.routefood.app.R;
import com.routefood.app.core.auth.RoleManager;
import com.routefood.app.core.auth.UserRole;
import com.routefood.app.core.ui.BaseActivity;

public class SelectRoleActivity extends BaseActivity {
    private RoleManager roleManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_select_role);
        roleManager = new RoleManager(this);

        findViewById(R.id.userCard).setOnClickListener(view -> openHome(UserRole.USER));
        findViewById(R.id.driverCard).setOnClickListener(view -> openHome(UserRole.DRIVER));
    }

    private void openHome(UserRole role) {
        roleManager.setDemoRole(role);
        startActivity(roleManager.homeIntent(this));
        finishAffinity();
    }
}
