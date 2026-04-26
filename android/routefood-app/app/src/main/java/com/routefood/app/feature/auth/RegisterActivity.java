package com.routefood.app.feature.auth;

import android.os.Bundle;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;

public class RegisterActivity extends BaseActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_register);

        findViewById(R.id.backToLoginButton).setOnClickListener(view -> finish());
    }
}
