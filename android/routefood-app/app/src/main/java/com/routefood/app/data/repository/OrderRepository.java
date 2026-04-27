package com.routefood.app.data.repository;

import com.routefood.app.core.firebase.FunctionsClient;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.Order;

import java.util.Map;

public class OrderRepository {
    private final FunctionsClient functionsClient;
    private final FirebaseRefs refs;

    public OrderRepository(android.content.Context context) {
        functionsClient = new FunctionsClient(context);
        FirebaseRefs firebaseRefs;
        try {
            firebaseRefs = new FirebaseRefs();
        } catch (IllegalStateException error) {
            firebaseRefs = null;
        }
        refs = firebaseRefs;
    }

    public boolean functionsAvailable() {
        return functionsClient.isAvailable();
    }

    public void createUserOrder(Map<String, Object> payload, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("createUserOrder", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    public com.google.firebase.firestore.ListenerRegistration listenOrder(String orderId, RepositoryCallback<Order> callback) {
        if (refs == null) {
            callback.onError(new IllegalStateException("Firebase Firestore is not configured."));
            return null;
        }
        return refs.orders().document(orderId).addSnapshotListener((snapshot, error) -> {
            if (error != null) {
                callback.onError(error);
                return;
            }
            if (snapshot == null || !snapshot.exists()) {
                callback.onError(new IllegalStateException("Order not found."));
                return;
            }
            callback.onSuccess(new Order(
                    snapshot.getId(),
                    snapshot.getString("userId"),
                    snapshot.getString("restaurantId"),
                    snapshot.getString("status"),
                    snapshot.getString("assignedDriverId"),
                    snapshot.getString("assignmentId"),
                    number(snapshot.get("total")).longValue(),
                    number(snapshot.get("etaMin")).intValue(),
                    GeoPoint.fromFirestore(snapshot.get("pickupLocation")),
                    GeoPoint.fromFirestore(snapshot.get("dropoffLocation"))));
        });
    }

    public com.google.firebase.database.Query listenDriverLocation(String driverId) {
        return com.google.firebase.database.FirebaseDatabase.getInstance()
                .getReference("driver_locations")
                .child(driverId);
    }

    private Number number(Object value) {
        return value instanceof Number ? (Number) value : 0;
    }
}
