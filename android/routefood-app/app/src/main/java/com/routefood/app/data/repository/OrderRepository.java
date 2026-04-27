package com.routefood.app.data.repository;

import com.routefood.app.core.firebase.FunctionsClient;

import java.util.Map;

public class OrderRepository {
    private final FunctionsClient functionsClient;

    public OrderRepository(android.content.Context context) {
        functionsClient = new FunctionsClient(context);
    }

    public boolean functionsAvailable() {
        return functionsClient.isAvailable();
    }

    public void createUserOrder(Map<String, Object> payload, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("createUserOrder", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }
}
