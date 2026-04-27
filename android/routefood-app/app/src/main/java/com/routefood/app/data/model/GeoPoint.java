package com.routefood.app.data.model;

public class GeoPoint {
    private final double latitude;
    private final double longitude;

    public GeoPoint(double latitude, double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public double latitude() {
        return latitude;
    }

    public double longitude() {
        return longitude;
    }

    public static GeoPoint fromFirestore(Object value) {
        if (value instanceof com.google.firebase.firestore.GeoPoint) {
            com.google.firebase.firestore.GeoPoint geoPoint = (com.google.firebase.firestore.GeoPoint) value;
            return new GeoPoint(geoPoint.getLatitude(), geoPoint.getLongitude());
        }
        return new GeoPoint(0, 0);
    }
}
