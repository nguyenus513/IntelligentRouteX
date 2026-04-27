package com.routefood.app.data.repository;

import com.routefood.app.core.firebase.FunctionsClient;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.data.model.Assignment;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DriverRepository {
    private final FunctionsClient functionsClient;
    private final FirebaseRefs refs;

    public DriverRepository(android.content.Context context) {
        functionsClient = new FunctionsClient(context);
        FirebaseRefs firebaseRefs;
        try {
            firebaseRefs = new FirebaseRefs();
        } catch (IllegalStateException error) {
            firebaseRefs = null;
        }
        refs = firebaseRefs;
    }

    public void setDriverOnline(Map<String, Object> payload, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("setDriverOnline", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void acceptAssignment(String assignmentId, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("driverAcceptAssignment", assignmentPayload(assignmentId))
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void rejectAssignment(String assignmentId, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("driverRejectAssignment", assignmentPayload(assignmentId))
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    private Map<String, Object> assignmentPayload(String assignmentId) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("assignmentId", assignmentId);
        return payload;
    }

    public com.google.firebase.firestore.ListenerRegistration listenActiveAssignments(String driverUid, RepositoryCallback<List<Assignment>> callback) {
        if (refs == null) {
            callback.onSuccess(new ArrayList<>());
            return null;
        }
        return refs.assignments()
                .whereEqualTo("driverUid", driverUid)
                .whereEqualTo("status", "assigned")
                .addSnapshotListener((snapshot, error) -> {
                    if (error != null) {
                        callback.onError(error);
                        return;
                    }
                    List<Assignment> assignments = new ArrayList<>();
                    if (snapshot != null) {
                        snapshot.forEach(document -> assignments.add(new Assignment(
                                document.getId(),
                                document.getString("driverId"),
                                orderIds(document.get("orderIds")),
                                document.getString("status"),
                                etaMinutes(document.get("eta")),
                                document.getString("risk"))));
                    }
                    callback.onSuccess(assignments);
                });
    }

    private List<String> orderIds(Object value) {
        List<String> ids = new ArrayList<>();
        if (value instanceof List<?>) {
            for (Object item : (List<?>) value) {
                if (item instanceof String) {
                    ids.add((String) item);
                }
            }
        }
        return ids;
    }

    private int etaMinutes(Object value) {
        if (value instanceof Map<?, ?>) {
            Object minutes = ((Map<?, ?>) value).get("minutes");
            if (minutes instanceof Number) {
                return ((Number) minutes).intValue();
            }
        }
        return 0;
    }
}
