package com.routefood.app.data.repository;

import com.routefood.app.core.firebase.FunctionsClient;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.data.model.Assignment;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.RouteStop;

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
        functionsClient.call("setSupabaseDriverOnline", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void acceptAssignment(String assignmentId, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("acceptSupabaseAssignment", assignmentPayload(assignmentId))
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void rejectAssignment(String assignmentId, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("rejectSupabaseAssignment", rejectPayload(assignmentId, "driver_declined"))
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void advanceAssignment(String assignmentId, String nextStatus, RepositoryCallback<Map<String, Object>> callback) {
        Map<String, Object> payload = assignmentPayload(assignmentId);
        payload.put("action", actionForStatus(nextStatus));
        functionsClient.call("advanceSupabaseAssignment", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void setDriverOffline(RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("setSupabaseDriverOffline", new HashMap<>())
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void updateDriverLocation(Map<String, Object> payload, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("updateSupabaseDriverLocation", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public void fetchActiveAssignment(RepositoryCallback<List<Assignment>> callback) {
        functionsClient.call("getSupabaseDriverAssignment", new HashMap<>())
                .addOnSuccessListener(value -> {
                    List<Assignment> assignments = new ArrayList<>();
                    Object assignmentObject = value.get("assignment");
                    if (assignmentObject instanceof Map<?, ?>) {
                        Map<?, ?> assignment = (Map<?, ?>) assignmentObject;
                        assignments.add(new Assignment(
                                String.valueOf(assignment.get("id")),
                                String.valueOf(assignment.get("driverId")),
                                orderIds(assignment.get("orderIds")),
                                String.valueOf(assignment.get("status")),
                                etaMinutes(assignment.get("eta")),
                                String.valueOf(assignment.get("risk")),
                                routeSummary(assignment.get("routePlan")),
                                routeSteps(assignment.get("routePlan")),
                                routeStops(assignment.get("routePlan"))));
                    }
                    callback.onSuccess(assignments);
                })
                .addOnFailureListener(callback::onError);
    }

    private Map<String, Object> assignmentPayload(String assignmentId) {
        Map<String, Object> payload = new HashMap<>();
        payload.put("assignmentId", assignmentId);
        return payload;
    }

    private Map<String, Object> rejectPayload(String assignmentId, String reason) {
        Map<String, Object> payload = assignmentPayload(assignmentId);
        payload.put("reason", reason);
        return payload;
    }

    private String actionForStatus(String status) {
        if ("PICKUP_ONE".equals(status)) return "arrived_at_restaurant";
        if ("PICKUP_TWO".equals(status)) return "picked_up";
        if ("DROPOFF_ONE".equals(status)) return "arrived_at_customer";
        if ("DROPOFF_TWO".equals(status) || "DELIVERED".equals(status)) return "delivered";
        return status;
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

    private String routeSummary(Object routePlan) {
        if (routePlan instanceof Map<?, ?>) {
            Object summary = ((Map<?, ?>) routePlan).get("summary");
            if (summary instanceof String && !((String) summary).isEmpty()) {
                return (String) summary;
            }
        }
        List<String> labels = new ArrayList<>();
        for (String step : routeSteps(routePlan)) {
            int separator = step.indexOf("  ");
            labels.add(separator > 0 ? step.substring(0, separator).trim() : step);
        }
        return labels.isEmpty() ? "P1 → P2 → D1 → D2" : String.join(" → ", labels);
    }

    private List<String> routeSteps(Object routePlan) {
        List<String> steps = new ArrayList<>();
        if (!(routePlan instanceof Map<?, ?>)) return steps;
        Object sequence = ((Map<?, ?>) routePlan).get("sequence");
        if (!(sequence instanceof List<?>)) return steps;
        for (Object value : (List<?>) sequence) {
            if (!(value instanceof Map<?, ?>)) continue;
            Map<?, ?> stop = (Map<?, ?>) value;
            String label = text(stop.get("label"), "S" + (steps.size() + 1));
            String title = text(stop.get("title"), text(stop.get("type"), "stop") + " " + text(stop.get("orderId"), ""));
            steps.add(label + "  " + title);
        }
        return steps;
    }

    private List<RouteStop> routeStops(Object routePlan) {
        List<RouteStop> stops = new ArrayList<>();
        if (!(routePlan instanceof Map<?, ?>)) return stops;
        Object sequence = ((Map<?, ?>) routePlan).get("sequence");
        if (!(sequence instanceof List<?>)) return stops;
        for (Object value : (List<?>) sequence) {
            if (!(value instanceof Map<?, ?>)) continue;
            Map<?, ?> stop = (Map<?, ?>) value;
            GeoPoint location = GeoPoint.fromFirestore(stop.get("location"));
            if (location.latitude() == 0 && location.longitude() == 0) continue;
            String label = text(stop.get("label"), "S" + (stops.size() + 1));
            String type = text(stop.get("type"), "stop");
            String orderId = text(stop.get("orderId"), "");
            String title = text(stop.get("title"), type + " " + orderId);
            stops.add(new RouteStop(label, title, type, orderId, location));
        }
        return stops;
    }

    private String text(Object value, String fallback) {
        return value instanceof String && !((String) value).isEmpty() ? (String) value : fallback;
    }
}
