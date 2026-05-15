package com.routechain.v2.schedule;

import java.util.List;
import java.util.Map;

public record RouteSchedule(
        String routeId,
        double totalKm,
        double durationMinutes,
        long lateOrderCount,
        double totalLatenessMinutes,
        List<StopSchedule> stopSchedules,
        Map<String, Double> etaByStop,
        Map<String, Double> deliveryEtaByOrder,
        Map<String, Double> slackByOrder,
        Map<String, OrderSchedule> orderSchedules,
        List<ScheduleViolation> violations) {

    public RouteSchedule {
        stopSchedules = stopSchedules == null ? List.of() : List.copyOf(stopSchedules);
        etaByStop = etaByStop == null ? Map.of() : Map.copyOf(etaByStop);
        deliveryEtaByOrder = deliveryEtaByOrder == null ? Map.of() : Map.copyOf(deliveryEtaByOrder);
        slackByOrder = slackByOrder == null ? Map.of() : Map.copyOf(slackByOrder);
        orderSchedules = orderSchedules == null ? Map.of() : Map.copyOf(orderSchedules);
        violations = violations == null ? List.of() : List.copyOf(violations);
    }
}
