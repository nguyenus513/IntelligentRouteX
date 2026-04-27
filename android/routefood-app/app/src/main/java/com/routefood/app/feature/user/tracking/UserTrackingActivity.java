package com.routefood.app.feature.user.tracking;

import android.os.Bundle;
import android.widget.TextView;

import com.routefood.app.R;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Order;
import com.routefood.app.data.repository.OrderRepository;
import com.routefood.app.data.repository.RepositoryCallback;

public class UserTrackingActivity extends BaseActivity {
    public static final String EXTRA_ORDER_ID = "order_id";
    private com.google.firebase.firestore.ListenerRegistration orderRegistration;
    private TextView statusText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_user_tracking);
        String orderId = getIntent().getStringExtra(EXTRA_ORDER_ID);
        statusText = findViewById(R.id.trackingStatusText);
        statusText.setText("Order " + orderId + " created.\nFinding and assigning a nearby demo driver...");
        orderRegistration = new OrderRepository(this).listenOrder(orderId, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Order order) {
                statusText.setText("Order " + order.id()
                        + "\nStatus: " + order.status()
                        + "\nDriver: " + safe(order.assignedDriverId())
                        + "\nETA: " + order.etaMin() + " min"
                        + "\nAssignment: " + safe(order.assignmentId()));
            }

            @Override
            public void onError(Exception error) {
                statusText.setText("Tracking is waiting for Firebase. Order: " + orderId);
            }
        });
    }

    @Override
    protected void onDestroy() {
        if (orderRegistration != null) {
            orderRegistration.remove();
        }
        super.onDestroy();
    }

    private String safe(String value) {
        return value == null || value.isEmpty() ? "pending" : value;
    }
}
