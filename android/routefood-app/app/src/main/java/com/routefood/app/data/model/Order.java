package com.routefood.app.data.model;

public class Order {
    private final String id;
    private final String userId;
    private final String restaurantId;
    private final String status;
    private final String assignedDriverId;
    private final String assignmentId;
    private final long total;
    private final int etaMin;

    public Order(String id, String userId, String restaurantId, String status, String assignedDriverId,
                 String assignmentId, long total, int etaMin) {
        this.id = id;
        this.userId = userId;
        this.restaurantId = restaurantId;
        this.status = status;
        this.assignedDriverId = assignedDriverId;
        this.assignmentId = assignmentId;
        this.total = total;
        this.etaMin = etaMin;
    }

    public String id() {
        return id;
    }

    public String userId() {
        return userId;
    }

    public String restaurantId() {
        return restaurantId;
    }

    public String status() {
        return status;
    }

    public String assignedDriverId() {
        return assignedDriverId;
    }

    public String assignmentId() {
        return assignmentId;
    }

    public long total() {
        return total;
    }

    public int etaMin() {
        return etaMin;
    }
}
