package com.routefood.app.data.repository;

import com.routefood.app.core.firebase.FunctionsClient;
import com.routefood.app.core.firebase.FirebaseRefs;
import com.routefood.app.core.auth.SessionStore;
import com.routefood.app.core.supabase.SupabaseConfig;
import com.routefood.app.core.supabase.SupabaseRestClient;
import com.routefood.app.core.supabase.SupabaseRpcClient;
import com.routefood.app.data.model.GeoPoint;
import com.routefood.app.data.model.Order;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import android.os.Handler;
import android.os.Looper;

public class OrderRepository {
    private final FunctionsClient functionsClient;
    private final FirebaseRefs refs;
    private final SessionStore sessionStore;
    private final SupabaseRpcClient supabaseRpcClient = new SupabaseRpcClient();
    private final SupabaseRestClient supabaseRestClient = new SupabaseRestClient();
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public OrderRepository(android.content.Context context) {
        functionsClient = new FunctionsClient(context);
        sessionStore = new SessionStore(context);
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
        if (SupabaseConfig.isConfigured() && sessionStore.getSupabaseAccessToken() != null) {
            createSupabaseOrder(payload, callback);
            return;
        }
        functionsClient.call("createUserOrder", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }

    private void createSupabaseOrder(Map<String, Object> payload, RepositoryCallback<Map<String, Object>> callback) {
        executor.execute(() -> {
            try {
                Map<?, ?> dropoff = (Map<?, ?>) payload.get("dropoffLocation");
                JSONObject rpcPayload = new JSONObject()
                        .put("p_restaurant_id", String.valueOf(payload.get("restaurantId")))
                        .put("p_dropoff_lat", number(dropoff == null ? null : dropoff.get("lat")).doubleValue())
                        .put("p_dropoff_lng", number(dropoff == null ? null : dropoff.get("lng")).doubleValue())
                        .put("p_items", itemsJson(payload.get("items")))
                        .put("p_payment_method", String.valueOf(payload.get("paymentMethod")));
                JSONObject result = supabaseRpcClient.call("create_customer_order", rpcPayload, sessionStore.getSupabaseAccessToken());
                Map<String, Object> response = new HashMap<>();
                response.put("orderId", result.optString("orderId"));
                response.put("orderCode", result.optString("orderCode"));
                response.put("status", result.optString("status"));
                response.put("total", result.optLong("total"));
                mainHandler.post(() -> callback.onSuccess(response));
            } catch (Exception error) {
                mainHandler.post(() -> callback.onError(error));
            }
        });
    }

    private JSONArray itemsJson(Object value) throws Exception {
        JSONArray array = new JSONArray();
        if (!(value instanceof java.util.List<?>)) return array;
        for (Object itemValue : (java.util.List<?>) value) {
            if (!(itemValue instanceof Map<?, ?>)) continue;
            Map<?, ?> item = (Map<?, ?>) itemValue;
            array.put(new JSONObject()
                    .put("itemId", String.valueOf(item.get("itemId")))
                    .put("name", String.valueOf(item.get("name")))
                    .put("price", number(item.get("price")).longValue())
                    .put("quantity", number(item.get("quantity")).intValue()));
        }
        return array;
    }

    public com.google.firebase.firestore.ListenerRegistration listenOrder(String orderId, RepositoryCallback<Order> callback) {
        if (SupabaseConfig.isConfigured() && sessionStore.getSupabaseAccessToken() != null) {
            fetchSupabaseOrder(orderId, callback);
            return null;
        }
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

    private void fetchSupabaseOrder(String orderId, RepositoryCallback<Order> callback) {
        Map<String, String> query = SupabaseRestClient.query();
        query.put("select", "id,user_id,restaurant_id,status,assigned_driver_id,assignment_id,total,promised_eta_minutes,pickup_location_json,dropoff_location_json");
        query.put("id", "eq." + orderId);
        query.put("limit", "1");
        supabaseRestClient.select("orders", query, sessionStore.getSupabaseAccessToken(), new SupabaseRestClient.JsonArrayCallback() {
            @Override
            public void onSuccess(JSONArray array) {
                if (array.length() == 0) {
                    callback.onError(new IllegalStateException("Order not found."));
                    return;
                }
                JSONObject json = array.optJSONObject(0);
                callback.onSuccess(new Order(
                        json.optString("id"),
                        json.optString("user_id"),
                        json.optString("restaurant_id"),
                        json.optString("status"),
                        json.optString("assigned_driver_id"),
                        json.optString("assignment_id"),
                        json.optLong("total"),
                        json.optInt("promised_eta_minutes"),
                        point(json.optJSONObject("pickup_location_json")),
                        point(json.optJSONObject("dropoff_location_json"))));
            }

            @Override
            public void onError(Exception error) {
                callback.onError(error);
            }
        });
    }

    private GeoPoint point(JSONObject json) {
        if (json == null) return new GeoPoint(10.7825, 106.7115);
        return new GeoPoint(json.optDouble("lat", 10.7825), json.optDouble("lng", 106.7115));
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
