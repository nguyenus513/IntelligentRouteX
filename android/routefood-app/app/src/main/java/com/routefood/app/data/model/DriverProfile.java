package com.routefood.app.data.model;

public class DriverProfile {
    private final String uid;
    private final String name;
    private final String vehicleType;
    private final double rating;
    private final boolean online;
    private final String status;

    public DriverProfile(String uid, String name, String vehicleType, double rating, boolean online, String status) {
        this.uid = uid;
        this.name = name;
        this.vehicleType = vehicleType;
        this.rating = rating;
        this.online = online;
        this.status = status;
    }

    public String uid() {
        return uid;
    }

    public String name() {
        return name;
    }

    public String vehicleType() {
        return vehicleType;
    }

    public double rating() {
        return rating;
    }

    public boolean online() {
        return online;
    }

    public String status() {
        return status;
    }
}
