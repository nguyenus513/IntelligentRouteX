package com.routefood.app.feature.driver;

import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.material.button.MaterialButton;
import com.routefood.app.R;
import com.routefood.app.core.auth.AuthManager;
import com.routefood.app.core.ui.BaseActivity;
import com.routefood.app.data.model.Assignment;
import com.routefood.app.data.repository.DriverRepository;
import com.routefood.app.data.repository.RepositoryCallback;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DriverMainActivity extends BaseActivity {
    private DriverRepository driverRepository;
    private TextView driverStatusText;
    private TextView assignmentSummaryText;
    private MaterialButton acceptButton;
    private MaterialButton rejectButton;
    private Assignment activeAssignment;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_driver_main);
        driverRepository = new DriverRepository(this);
        driverStatusText = findViewById(R.id.driverStatusText);
        assignmentSummaryText = findViewById(R.id.assignmentSummaryText);
        acceptButton = findViewById(R.id.acceptAssignmentButton);
        rejectButton = findViewById(R.id.rejectAssignmentButton);

        findViewById(R.id.goOnlineButton).setOnClickListener(view -> goOnline());
        acceptButton.setOnClickListener(view -> acceptActiveAssignment());
        rejectButton.setOnClickListener(view -> rejectActiveAssignment());

        listenAssignments();
    }

    private void goOnline() {
        Map<String, Object> location = new HashMap<>();
        location.put("lat", 10.7741);
        location.put("lng", 106.7038);
        Map<String, Object> payload = new HashMap<>();
        payload.put("online", true);
        payload.put("location", location);
        driverRepository.setDriverOnline(payload, new RepositoryCallback<>() {
            @Override
            public void onSuccess(Map<String, Object> value) {
                driverStatusText.setText("Online");
                Toast.makeText(DriverMainActivity.this, "Driver is online.", Toast.LENGTH_SHORT).show();
            }

            @Override
            public void onError(Exception error) {
                Toast.makeText(DriverMainActivity.this, error.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    private void listenAssignments() {
        AuthManager authManager = new AuthManager(this);
        String uid = authManager.currentUser() == null ? "demo-driver-q1" : authManager.currentUser().getUid();
        driverRepository.listenActiveAssignments(uid, new RepositoryCallback<>() {
            @Override
            public void onSuccess(List<Assignment> assignments) {
                if (assignments.isEmpty()) {
                    activeAssignment = null;
                    assignmentSummaryText.setText("Waiting for assignment...");
                    acceptButton.setEnabled(false);
                    rejectButton.setEnabled(false);
                    return;
                }
                activeAssignment = assignments.get(0);
                assignmentSummaryText.setText("New assignment " + activeAssignment.id()
                        + "\nETA: " + activeAssignment.etaMin() + " min\nRisk: " + activeAssignment.risk());
                acceptButton.setEnabled(true);
                rejectButton.setEnabled(true);
            }

            @Override
            public void onError(Exception error) {
                assignmentSummaryText.setText("Assignment listener unavailable. Use Firebase config/emulator for live data.");
            }
        });
    }

    private void acceptActiveAssignment() {
        if (activeAssignment == null) {
            return;
        }
        driverRepository.acceptAssignment(activeAssignment.id(), simpleToast("Assignment accepted."));
    }

    private void rejectActiveAssignment() {
        if (activeAssignment == null) {
            return;
        }
        driverRepository.rejectAssignment(activeAssignment.id(), simpleToast("Assignment rejected."));
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
}
