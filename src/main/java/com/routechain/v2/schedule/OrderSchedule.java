package com.routechain.v2.schedule;

public record OrderSchedule(
        String orderId,
        double deliveryEtaMinutes,
        double dueTimeMinutes,
        double slackMinutes,
        double latenessMinutes,
        boolean late) {
}
