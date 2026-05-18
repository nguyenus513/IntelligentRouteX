package com.routechain.v2.seedimprovement;

public record PdStop(
        String orderId,
        PdStopType type,
        double lat,
        double lng,
        int serviceMinutes,
        int loadDelta,
        double deadlineMinutes) {

    public PdStop {
        orderId = orderId == null ? "" : orderId;
    }

    public enum PdStopType {
        PICKUP,
        DROPOFF
    }
}
