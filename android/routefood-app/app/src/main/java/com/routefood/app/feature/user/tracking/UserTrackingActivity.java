package com.routefood.app.feature.user.tracking;

import android.os.Bundle;
import android.widget.TextView;

import com.routefood.app.R;
import com.routefood.app.core.map.DemoMapView;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.Order;
import com.routefood.app.data.repository.OrderRepository;
import com.routefood.app.data.repository.RepositoryCallback;

public class UserTrackingActivity extends BaseActivity {
    public static final String EXTRA_ORDER_ID = "order_id";
    private com.google.firebase.firestore.ListenerRegistration orderRegistration;
    private TextView statusText;
    private DemoMapView mapView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_user_tracking);
        String orderId = getIntent().getStringExtra(EXTRA_ORDER_ID);
        statusText = findViewById(R.id.trackingStatusText);
        mapView = findViewById(R.id.userTrackingMapView);
        statusText.setText("Order " + orderId + " created.\nFinding and assigning a nearby demo driver...");
        orderRegistration = new OrderRepository(this).listenOrder(orderId, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Order order) {
                GeoPoint driverPoint = simulatedDriverPoint(order);
                mapView.setRoute(order.pickupLocation(), order.dropoffLocation(), driverPoint,
                        "Status: " + order.status() + " • ETA " + order.etaMin() + " min");
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

    private GeoPoint simulatedDriverPoint(Order order) {
        if ("DRIVER_TO_RESTAURANT".equals(order.status())) {
            return midpoint(order.pickupLocation(), order.dropoffLocation(), 0.25);
        }
        if ("PICKING_UP".equals(order.status())) {
            return order.pickupLocation();
        }
        if ("DRIVER_TO_USER".equals(order.status()) || "ARRIVING".equals(order.status())) {
            return midpoint(order.pickupLocation(), order.dropoffLocation(), 0.75);
        }
        return midpoint(order.pickupLocation(), order.dropoffLocation(), 0.05);
    }

    private GeoPoint midpoint(GeoPoint from, GeoPoint to, double progress) {
        return new GeoPoint(
                from.latitude() + ((to.latitude() - from.latitude()) * progress),
                from.longitude() + ((to.longitude() - from.longitude()) * progress));
    }
}
