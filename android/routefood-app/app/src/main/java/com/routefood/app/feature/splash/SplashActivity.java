package com.routefood.app.feature.splash;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;

import com.routefood.app.R;
import com.routefood.app.core.auth.RoleManager;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.feature.auth.LoginActivity;

public class SplashActivity extends BaseActivity {
    private RoleManager roleManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_splash);
        roleManager = new RoleManager(this);

        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (!roleManager.hasSignedInUser()) {
                startActivity(new Intent(this, LoginActivity.class));
                finish();
                return;
            }
            roleManager.resolveRole().addOnCompleteListener(task -> {
                startActivity(roleManager.homeIntent(this, task.getResult()));
                finish();
            });
        }, 600L);
    }
}
