package com.routefood.app.feature.driver.navigation;

import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.material.button.MaterialButton;
import com.routefood.app.R;
import com.routefood.app.core.map.DemoMapView;
import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.repository.DriverRepository;
import com.routefood.app.data.repository.RepositoryCallback;

import java.util.List;
import java.util.Map;

public class DriverNavigationActivity extends BaseActivity {
    public static final String EXTRA_ASSIGNMENT_ID = "assignment_id";
    private final String[] statuses = {"PICKING_UP", "DRIVER_TO_USER", "ARRIVING", "DELIVERED"};
    private int statusIndex = 0;
    private String assignmentId;
    private TextView instructionText;
    private MaterialButton nextButton;
    private DriverRepository driverRepository;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_driver_navigation);
        assignmentId = getIntent().getStringExtra(EXTRA_ASSIGNMENT_ID);
        instructionText = findViewById(R.id.navigationInstructionText);
        nextButton = findViewById(R.id.nextNavigationStepButton);
        driverRepository = new DriverRepository(this);
        setupMap();
        nextButton.setOnClickListener(view -> advance());
    }

    private void setupMap() {
        DemoMapView mapView = findViewById(R.id.driverNavigationMapView);
        GeoPoint driver = new GeoPoint(10.776, 106.704);
        GeoPoint pickup = new GeoPoint(10.7741, 106.7038);
        GeoPoint dropoff = new GeoPoint(10.7942, 106.7218);
        mapView.setRoute(pickup, dropoff, driver, "Navigation " + assignmentId);
        new OsrmRouteClient().route(driver, pickup, dropoff, new OsrmRouteClient.Callback() {
            @Override
            public void onRoute(List<GeoPoint> routePoints) {
                mapView.setRoadRoute(routePoints);
            }

            @Override
            public void onError(Exception error) {
            }
        });
    }

    private void advance() {
        String nextStatus = statuses[statusIndex];
        driverRepository.advanceAssignment(assignmentId, nextStatus, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                statusIndex = Math.min(statusIndex + 1, statuses.length - 1);
                updateInstruction(nextStatus);
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverNavigationActivity.this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    private void updateInstruction(String completedStatus) {
        if ("PICKING_UP".equals(completedStatus)) {
            instructionText.setText("Pickup confirmed. Head to customer.");
            nextButton.setText("Picked up");
        } else if ("DRIVER_TO_USER".equals(completedStatus)) {
            instructionText.setText("On the way to customer.");
            nextButton.setText("Arriving customer");
        } else if ("ARRIVING".equals(completedStatus)) {
            instructionText.setText("Arriving now. Complete delivery when handed off.");
            nextButton.setText("Complete delivery");
        } else {
            instructionText.setText("Delivery completed.");
            nextButton.setEnabled(false);
        }
    }
}
