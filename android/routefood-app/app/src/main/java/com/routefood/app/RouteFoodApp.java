package com.routefood.app;

import android.app.Application;

import org.maplibre.android.MapLibre;
import org.maplibre.android.WellKnownTileServer;

public class RouteFoodApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        MapLibre.getInstance(this, "", WellKnownTileServer.MapLibre);
    }
}
