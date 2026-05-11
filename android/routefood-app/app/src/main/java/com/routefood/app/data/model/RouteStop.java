package com.routefood.app.data.model;

public class RouteStop {
    private final String label;
    private final String title;
    private final String type;
    private final String orderId;
    private final GeoPoint location;

    public RouteStop(String label, String title, String type, String orderId, GeoPoint location) {
        this.label = label;
        this.title = title;
        this.type = type;
        this.orderId = orderId;
        this.location = location;
    }

    public String label() {
        return label;
    }

    public String title() {
        return title;
    }

    public String type() {
        return type;
    }

    public String orderId() {
        return orderId;
    }

    public GeoPoint location() {
        return location;
    }
}
