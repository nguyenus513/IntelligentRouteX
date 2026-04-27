package com.routefood.app.feature.user.tracking;

import android.os.Bundle;
import android.widget.TextView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;

public class UserTrackingActivity extends BaseActivity {
    public static final String EXTRA_ORDER_ID = "order_id";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_user_tracking);
        String orderId = getIntent().getStringExtra(EXTRA_ORDER_ID);
        ((TextView) findViewById(R.id.trackingStatusText)).setText(
                "Order " + orderId + " created.\nFinding and assigning a nearby demo driver...");
    }
}
