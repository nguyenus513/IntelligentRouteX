package com.routechain.v2.schedule;

public record ScheduleViolation(String routeId, String orderId, String violationType, double amountMinutes, String reason) {
}
