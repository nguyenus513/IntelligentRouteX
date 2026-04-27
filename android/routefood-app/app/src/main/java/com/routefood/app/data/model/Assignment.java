package com.routefood.app.data.model;

import java.util.List;

public class Assignment {
    private final String id;
    private final String driverId;
    private final List<String> orderIds;
    private final String status;
    private final int etaMin;
    private final String risk;

    public Assignment(String id, String driverId, List<String> orderIds, String status, int etaMin, String risk) {
        this.id = id;
        this.driverId = driverId;
        this.orderIds = orderIds;
        this.status = status;
        this.etaMin = etaMin;
        this.risk = risk;
    }

    public String id() {
        return id;
    }

    public String driverId() {
        return driverId;
    }

    public List<String> orderIds() {
        return orderIds;
    }

    public String status() {
        return status;
    }

    public int etaMin() {
        return etaMin;
    }

    public String risk() {
        return risk;
    }
}
