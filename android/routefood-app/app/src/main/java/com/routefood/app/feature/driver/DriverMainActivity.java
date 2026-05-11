package com.routefood.app.feature.driver;

import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.material.button.MaterialButton;
import com.routefood.app.R;
import com.routefood.app.core.auth.AuthManager;
import com.routefood.app.core.map.LeafletMapView;
import com.routefood.app.core.map.OsrmRouteClient;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Assignment;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.RouteStop;
import com.routefood.app.data.repository.DriverRepository;
import com.routefood.app.data.repository.RepositoryCallback;
import com.routefood.app.feature.driver.navigation.DriverNavigationActivity;

import java.util.Arrays;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DriverMainActivity extends BaseActivity {
    private DriverRepository driverRepository;
    private TextView driverStatusText;
    private TextView assignmentSummaryText;
    private MaterialButton goOnlineButton;
    private MaterialButton acceptButton;
    private MaterialButton rejectButton;
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
        setContentView(R.layout.activity_driver_main);
        driverRepository = new DriverRepository(this);
        driverStatusText = findViewById(R.id.driverStatusText);
        assignmentSummaryText = findViewById(R.id.assignmentSummaryText);
        goOnlineButton = findViewById(R.id.goOnlineButton);
        acceptButton = findViewById(R.id.acceptAssignmentButton);
        rejectButton = findViewById(R.id.rejectAssignmentButton);
        mapView = findViewById(R.id.driverMapView);
        renderBatchRoute("Batch route Ã¢â‚¬Â¢ 2 orders");

        goOnlineButton.setOnClickListener(view -> goOnline());
        acceptButton.setOnClickListener(view -> acceptActiveAssignment());
        rejectButton.setOnClickListener(view -> rejectActiveAssignment());

        listenAssignments();
        refreshSupabaseAssignment();
    }

    private void goOnline() {
        driverStatusText.setText("ONLINE");
        driverStatusText.setTextColor(getColor(R.color.route_success));
        goOnlineButton.setText("SEARCHING BATCHES");
        Map<String, Object> location = new HashMap<>();
        location.put("lat", driverPoint.latitude());
        location.put("lng", driverPoint.longitude());
        Map<String, Object> payload = new HashMap<>();
        payload.put("online", true);
        payload.put("zoneId", "d1-nguyen-hue");
        payload.put("location", location);
        driverRepository.setDriverOnline(payload, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                Toast.makeText(DriverMainActivity.this, "You are online.", Toast.LENGTH_SHORT).show();
                refreshSupabaseAssignment();
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverMainActivity.this, "Online demo mode enabled.", Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void listenAssignments() {
        AuthManager authManager = new AuthManager(this);
        String uid = authManager.currentUser() == null ? "demo-driver-q1" : authManager.currentUser().getUid();
        driverRepository.listenActiveAssignments(uid, new RepositoryCallback<List<Assignment>>() {
            @Override
            public void onSuccess(List<Assignment> assignments) {
                if (assignments.isEmpty()) {
                    assignmentSummaryText.setText("Đang chờ assignment từ Supabase\nApp chỉ hiển thị routePlan do Assignment Gateway ghi lên Supabase.");
                    return;
                }
                activeAssignment = assignments.get(0);
                goOnlineButton.setText("BATCH AVAILABLE");
                renderAssignment(activeAssignment, "Live batch • " + activeAssignment.orderIds().size() + " orders");
            }

            @Override
            public void onError(Exception error) {
                assignmentSummaryText.setText("Chưa tải được assignment từ backend. Kiểm tra Supabase/Functions.");
            }
        });
    }

    private void refreshSupabaseAssignment() {
        driverRepository.fetchActiveAssignment(new RepositoryCallback<List<Assignment>>() {
            @Override
            public void onSuccess(List<Assignment> assignments) {
                if (assignments.isEmpty()) {
                    return;
                }
                activeAssignment = assignments.get(0);
                goOnlineButton.setText("BATCH AVAILABLE");
                renderAssignment(activeAssignment, "Supabase routePlan • " + activeAssignment.orderIds().size() + " orders");
            }

            @Override
            public void onError(Exception error) {
                // Keep Firestore listener/demo fallback visible while Supabase polling is unavailable.
            }
        });
    }

    private void acceptActiveAssignment() {
        if (activeAssignment == null) {
            Intent intent = new Intent(this, DriverNavigationActivity.class);
            intent.putExtra(DriverNavigationActivity.EXTRA_ASSIGNMENT_ID, "demo-batch-assignment");
            startActivity(intent);
            return;
        }
        driverRepository.acceptAssignment(activeAssignment.id(), new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                Intent intent = new Intent(DriverMainActivity.this, DriverNavigationActivity.class);
                intent.putExtra(DriverNavigationActivity.EXTRA_ASSIGNMENT_ID, activeAssignment.id());
                startActivity(intent);
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverMainActivity.this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    private void rejectActiveAssignment() {
        if (activeAssignment == null) {
            Toast.makeText(this, "Batch declined.", Toast.LENGTH_SHORT).show();
            return;
        }
        driverRepository.rejectAssignment(activeAssignment.id(), simpleToast("Batch declined."));
    }

    private RepositoryCallback<Map<String, Object>> simpleToast(String message) {
        return new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                Toast.makeText(DriverMainActivity.this, message, Toast.LENGTH_SHORT).show();
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverMainActivity.this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        };
    }

    private void renderAssignment(Assignment assignment, String mapLabel) {
        StringBuilder summary = new StringBuilder();
        summary.append("Assignment: ").append(assignment.id()).append('\n');
        summary.append(assignment.orderIds().size()).append(" orders từ IntelligentRouteX • ETA ").append(assignment.etaMin()).append(" min • Risk ").append(assignment.risk()).append('\n');
        if (assignment.routeSummary() != null && !assignment.routeSummary().isEmpty()) {
            summary.append(assignment.routeSummary()).append('\n');
        }
        List<String> steps = assignment.routeSteps();
        for (int index = 0; index < Math.min(steps.size(), 5); index++) {
            summary.append("• ").append(steps.get(index)).append('\n');
        }
        assignmentSummaryText.setText(summary.toString().trim());
        renderRoutePlanOrFallback(assignment, mapLabel);
    }

    private void renderRoutePlanOrFallback(Assignment assignment, String label) {
        if (assignment.routeStops().isEmpty()) {
            renderBatchRoute(label);
            return;
        }
        List<GeoPoint> waypoints = new ArrayList<>();
        waypoints.add(driverPoint);
        for (RouteStop stop : assignment.routeStops()) {
            waypoints.add(stop.location());
        }
        mapView.setRoutePlan(driverPoint, assignment.routeStops(), waypoints, label, nonEmpty(assignment.routeSummary(), "mobile-route-plan/v1"));
        routeClient.routeWaypoints(waypoints, new OsrmRouteClient.Callback() {
            @Override
            public void onRoute(List<GeoPoint> routePoints) {
                mapView.setRoutePlan(driverPoint, assignment.routeStops(), routePoints, label, nonEmpty(assignment.routeSummary(), "Road route via OSRM"));
            }

            @Override
            public void onError(Exception error) {
                mapView.setRoutePlan(driverPoint, assignment.routeStops(), waypoints, label, "OSRM unavailable - routePlan fallback");
            }
        });
    }

    private String nonEmpty(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }

    private void renderBatchRoute(String label) {
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
}
