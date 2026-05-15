package com.routechain.v2.schedule;

public record SchedulePolicy(
        double speedKmh,
        double pickupServiceMinutes,
        double dropoffServiceMinutes,
        String policyVersion) {

    public SchedulePolicy {
        speedKmh = speedKmh <= 0.0 ? 22.0 : speedKmh;
        pickupServiceMinutes = Math.max(0.0, pickupServiceMinutes);
        dropoffServiceMinutes = Math.max(0.0, dropoffServiceMinutes);
        policyVersion = policyVersion == null || policyVersion.isBlank() ? "schedule-policy/v1" : policyVersion;
    }

    public static SchedulePolicy defaults() {
        return new SchedulePolicy(22.0, 0.0, 0.0, "schedule-policy/v1");
    }
}
