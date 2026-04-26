package com.routefood.app;

import android.app.Application;

import com.google.firebase.FirebaseApp;

public class RouteFoodApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        try {
            FirebaseApp.initializeApp(this);
        } catch (IllegalStateException ignored) {
        }
    }
}
