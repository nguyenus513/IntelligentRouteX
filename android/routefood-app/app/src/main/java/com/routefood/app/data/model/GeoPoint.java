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
        if (value instanceof java.util.Map<?, ?>) {
            java.util.Map<?, ?> map = (java.util.Map<?, ?>) value;
            Object lat = map.get("lat");
            Object lng = map.get("lng");
            if (lat instanceof Number && lng instanceof Number) {
                return new GeoPoint(((Number) lat).doubleValue(), ((Number) lng).doubleValue());
            }
        }
        return new GeoPoint(0, 0);
    }
}
