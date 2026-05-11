package com.routefood.app.feature.driver.navigation;

import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.material.button.MaterialButton;
import com.routefood.app.R;
import com.routefood.app.core.map.LeafletMapView;
import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Assignment;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.RouteStop;
import com.routefood.app.data.repository.DriverRepository;
import com.routefood.app.data.repository.RepositoryCallback;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

public class DriverNavigationActivity extends BaseActivity {
    public static final String EXTRA_ASSIGNMENT_ID = "assignment_id";
    private final String[] statuses = {"PICKUP_ONE", "PICKUP_TWO", "DROPOFF_ONE", "DROPOFF_TWO", "DELIVERED"};
    private int statusIndex = 0;
    private String assignmentId;
    private TextView titleText;
    private TextView instructionText;
    private MaterialButton nextButton;
    private DriverRepository driverRepository;
    private LeafletMapView mapView;
    private final OsrmRouteClient routeClient = new OsrmRouteClient();
    private Assignment activeAssignment;

    private final GeoPoint driverPoint = new GeoPoint(10.776, 106.704);
    private final GeoPoint pickupPoint = new GeoPoint(10.7741, 106.7038);
    private final GeoPoint pickupTwoPoint = new GeoPoint(10.7798, 106.7087);
    private final GeoPoint dropoffPoint = new GeoPoint(10.7942, 106.7218);
    private final GeoPoint dropoffTwoPoint = new GeoPoint(10.7956, 106.7229);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_driver_navigation);
        assignmentId = getIntent().getStringExtra(EXTRA_ASSIGNMENT_ID);
        titleText = findViewById(R.id.navigationTitleText);
        instructionText = findViewById(R.id.navigationInstructionText);
        nextButton = findViewById(R.id.nextNavigationStepButton);
        mapView = findViewById(R.id.driverNavigationMapView);
        driverRepository = new DriverRepository(this);
        setupMap("P1 next • 8 min");
        loadAssignmentRoutePlan();
        nextButton.setOnClickListener(view -> advance());
    }

    private void loadAssignmentRoutePlan() {
        driverRepository.fetchActiveAssignment(new RepositoryCallback<List<Assignment>>() {
            @Override
            public void onSuccess(List<Assignment> assignments) {
                if (assignments.isEmpty()) {
                    return;
                }
                Assignment assignment = assignments.get(0);
                if (assignmentId != null && !assignmentId.equals(assignment.id())) {
                    return;
                }
                activeAssignment = assignment;
                renderNavigationAssignment();
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverNavigationActivity.this, "Không tải được routePlan từ Supabase.", Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void renderNavigationAssignment() {
        if (activeAssignment == null || activeAssignment.routeStops().isEmpty()) {
            return;
        }
        RouteStop currentStop = activeAssignment.routeStops().get(Math.min(statusIndex, activeAssignment.routeStops().size() - 1));
        titleText.setText("RoutePlan " + nonEmpty(activeAssignment.routeSummary(), "mobile-route-plan/v1"));
        instructionText.setText(currentStop.label() + " - " + currentStop.title() + "\nAssignment " + activeAssignment.id() + " • " + activeAssignment.orderIds().size() + " orders");
        nextButton.setText(buttonTextFor(currentStop));
        setupRoutePlan(currentStop.label() + " next");
    }

    private void setupRoutePlan(String label) {
        if (activeAssignment == null || activeAssignment.routeStops().isEmpty()) {
            return;
        }
        List<GeoPoint> waypoints = new ArrayList<>();
        waypoints.add(driverPoint);
        for (RouteStop stop : activeAssignment.routeStops()) {
            waypoints.add(stop.location());
        }
        mapView.setRoutePlan(driverPoint, activeAssignment.routeStops(), waypoints, label, nonEmpty(activeAssignment.routeSummary(), "mobile-route-plan/v1"));
        routeClient.routeWaypoints(waypoints, new OsrmRouteClient.Callback() {
            @Override
            public void onRoute(List<GeoPoint> routePoints) {
                mapView.setRoutePlan(driverPoint, activeAssignment.routeStops(), routePoints, label, nonEmpty(activeAssignment.routeSummary(), "Road route via OSRM"));
            }

            @Override
            public void onError(Exception error) {
                mapView.setRoutePlan(driverPoint, activeAssignment.routeStops(), waypoints, label, "OSRM unavailable - routePlan fallback");
            }
        });
    }

    private String buttonTextFor(RouteStop stop) {
        if ("pickup".equals(stop.type())) {
            return "COMPLETE " + stop.label();
        }
        if ("dropoff".equals(stop.type())) {
            return "DELIVER " + stop.label();
        }
        return "COMPLETE STEP";
    }

    private String nonEmpty(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }

    private void setupMap(String label) {
        renderBatchFallback(label);
        routeClient.routeLeg(driverPoint, pickupPoint, new OsrmRouteClient.Callback() {
            @Override
            public void onRoute(List<GeoPoint> driverToPickupOne) {
                routeClient.routeLeg(pickupPoint, pickupTwoPoint, new OsrmRouteClient.Callback() {
                    @Override
                    public void onRoute(List<GeoPoint> pickupOneToPickupTwo) {
                        routeClient.routeLeg(pickupTwoPoint, dropoffPoint, new OsrmRouteClient.Callback() {
                            @Override
                            public void onRoute(List<GeoPoint> pickupTwoToDropoffOne) {
                                routeClient.routeLeg(dropoffPoint, dropoffTwoPoint, new OsrmRouteClient.Callback() {
                                    @Override
                                    public void onRoute(List<GeoPoint> dropoffOneToDropoffTwo) {
                                        mapView.setBatchRoute(driverPoint, pickupPoint, pickupTwoPoint, dropoffPoint, dropoffTwoPoint, driverToPickupOne, pickupOneToPickupTwo, pickupTwoToDropoffOne, dropoffOneToDropoffTwo, label, "Road route via OSRM");
                                    }

                                    @Override
                                    public void onError(Exception error) {
                                        mapView.setBatchRoute(driverPoint, pickupPoint, pickupTwoPoint, dropoffPoint, dropoffTwoPoint, driverToPickupOne, pickupOneToPickupTwo, pickupTwoToDropoffOne, Arrays.asList(dropoffPoint, dropoffTwoPoint), label, "Partial OSRM route");
                                    }
                                });
                            }

                            @Override
                            public void onError(Exception error) {
                                renderBatchFallback(label);
                            }
                        });
                    }

                    @Override
                    public void onError(Exception error) {
                        renderBatchFallback(label);
                    }
                });
            }

            @Override
            public void onError(Exception error) {
                renderBatchFallback(label);
            }
        });
    }

    private void renderBatchFallback(String label) {
        mapView.setBatchRoute(
                driverPoint,
                pickupPoint,
                pickupTwoPoint,
                dropoffPoint,
                dropoffTwoPoint,
                Arrays.asList(driverPoint, pickupPoint),
                Arrays.asList(pickupPoint, pickupTwoPoint),
                Arrays.asList(pickupTwoPoint, dropoffPoint),
                Arrays.asList(dropoffPoint, dropoffTwoPoint),
                label,
                "OSRM unavailable - straight fallback");
    }

    private void advance() {
        String nextStatus = statuses[statusIndex];
        if (assignmentId == null || "demo-assignment".equals(assignmentId) || "demo-batch-assignment".equals(assignmentId)) {
            statusIndex = Math.min(statusIndex + 1, statuses.length - 1);
            if (activeAssignment == null) {
                updateInstruction(nextStatus);
            } else {
                renderNavigationAssignment();
            }
            return;
        }
        driverRepository.advanceAssignment(assignmentId, nextStatus, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                statusIndex = Math.min(statusIndex + 1, statuses.length - 1);
                if (activeAssignment == null) {
                    updateInstruction(nextStatus);
                } else {
                    renderNavigationAssignment();
                }
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverNavigationActivity.this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    private void updateInstruction(String completedStatus) {
        if ("PICKUP_ONE".equals(completedStatus)) {
            titleText.setText("Batch route Ã¢â‚¬Â¢ P2 next Ã¢â‚¬Â¢ 4 min");
            instructionText.setText("Stop P2: Kuro Sushi\nOrder N-4822 Ã¢â‚¬Â¢ 2 items Ã¢â‚¬Â¢ add to batch bag\nNext: D1 Saigon Pearl");
            nextButton.setText("ARRIVED AT P2");
            setupMap("P2 next Ã¢â‚¬Â¢ 4 min");
        } else if ("PICKUP_TWO".equals(completedStatus)) {
            titleText.setText("Batch route Ã¢â‚¬Â¢ D1 next Ã¢â‚¬Â¢ 9 min");
            instructionText.setText("Dropoff D1: Saigon Pearl lobby\nCustomer A Ã¢â‚¬Â¢ leave at reception if no answer\nNext: D2 Landmark 81");
            nextButton.setText("COMPLETE D1");
            setupMap("D1 next Ã¢â‚¬Â¢ 9 min");
        } else if ("DROPOFF_ONE".equals(completedStatus)) {
            titleText.setText("Batch route Ã¢â‚¬Â¢ D2 final Ã¢â‚¬Â¢ 5 min");
            instructionText.setText("Dropoff D2: Landmark 81 area\nCustomer B Ã¢â‚¬Â¢ COD Ã¢â‚¬Â¢ call at lobby\nFinal stop in this batch");
            nextButton.setText("COMPLETE D2");
            setupMap("D2 final Ã¢â‚¬Â¢ 5 min");
        } else if ("DROPOFF_TWO".equals(completedStatus)) {
            titleText.setText("Batch completed");
            instructionText.setText("2 orders delivered\n+$11.40 added Ã¢â‚¬Â¢ 11 min saved by batching");
            nextButton.setText("DONE");
            nextButton.setEnabled(false);
        } else {
            titleText.setText("Batch completed");
            instructionText.setText("Great job. Earnings added to today balance.");
            nextButton.setText("DONE");
            nextButton.setEnabled(false);
        }
    }
}
