package com.routefood.app.feature.auth;

import android.content.Intent;
import android.os.Bundle;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;

public class LoginActivity extends BaseActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        findViewById(R.id.loginButton).setOnClickListener(view ->
                startActivity(new Intent(this, SelectRoleActivity.class)));
        findViewById(R.id.registerButton).setOnClickListener(view ->
                startActivity(new Intent(this, RegisterActivity.class)));
    }
}
