package com.routefood.app.data.model;

public class TrafficHotspot {
    private final String id;
    private final String name;
    private final GeoPoint center;
    private final int radiusMeters;
    private final String level;

    public TrafficHotspot(String id, String name, GeoPoint center, int radiusMeters, String level) {
        this.id = id;
        this.name = name;
        this.center = center;
        this.radiusMeters = radiusMeters;
        this.level = level;
    }

    public String id() {
        return id;
    }

    public String name() {
        return name;
    }

    public GeoPoint center() {
        return center;
    }

    public int radiusMeters() {
        return radiusMeters;
    }

    public String level() {
        return level;
    }
}
