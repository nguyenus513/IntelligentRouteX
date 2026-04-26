package com.routefood.app.core.firebase;

import android.content.Context;

import com.google.android.gms.tasks.Task;
import com.google.android.gms.tasks.Tasks;
import com.google.firebase.FirebaseApp;
import com.google.firebase.functions.FirebaseFunctions;

import java.util.HashMap;
import java.util.Map;

public class FunctionsClient {
    private final FirebaseFunctions functions;

    public FunctionsClient(Context context) {
        FirebaseFunctions firebaseFunctions = null;
        if (!FirebaseApp.getApps(context.getApplicationContext()).isEmpty()) {
            try {
                firebaseFunctions = FirebaseFunctions.getInstance();
            } catch (IllegalStateException ignored) {
                firebaseFunctions = null;
            }
        }
        functions = firebaseFunctions;
    }

    public boolean isAvailable() {
        return functions != null;
    }

    public Task<Map<String, Object>> bootstrapDemoRole(String role) {
        if (functions == null) {
            Map<String, Object> localResult = new HashMap<>();
            localResult.put("role", role);
            return Tasks.forResult(localResult);
        }
        Map<String, Object> payload = new HashMap<>();
        payload.put("role", role);
        return functions
                .getHttpsCallable("bootstrapDemoRole")
                .call(payload)
                .continueWith(task -> {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> data = (Map<String, Object>) task.getResult().getData();
                    return data;
                });
    }
}
