package com.routefood.app.data.repository;

import com.routefood.app.core.firebase.FunctionsClient;

import java.util.Map;

public class DriverRepository {
    private final FunctionsClient functionsClient;

    public DriverRepository(android.content.Context context) {
        functionsClient = new FunctionsClient(context);
    }

    public void setDriverOnline(Map<String, Object> payload, RepositoryCallback<Map<String, Object>> callback) {
        functionsClient.call("setDriverOnline", payload)
                .addOnSuccessListener(callback::onSuccess)
                .addOnFailureListener(callback::onError);
    }
}
