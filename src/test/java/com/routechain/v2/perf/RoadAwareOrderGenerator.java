package com.routechain.v2.perf;

import com.routechain.domain.Order;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

final class RoadAwareOrderGenerator {
    private final RoadAwareMerchantSampler merchantSampler = new RoadAwareMerchantSampler();
    private final RoadAwareCustomerSampler customerSampler = new RoadAwareCustomerSampler();

    List<Order> generate(int orderCount, DispatchPerfWorkloadFactory.ScenarioWorldProfile profile) {
        List<Order> orders = new ArrayList<>(orderCount);
        for (int index = 0; index < orderCount; index++) {
            int offset = index % 4;
            Instant readyAt = profile.decisionTime().plusSeconds((long) (offset % profile.readyBucketSpan()) * profile.readyStepSeconds());
            orders.add(new Order(
                    "order-" + index,
                    merchantSampler.sample(index),
                    customerSampler.sample(index),
                    readyAt.minusSeconds(300),
                    readyAt,
                    profile.baseReadyWindowMinutes() + (offset % profile.readyWindowSpread()),
                    index % profile.priorityInterval() == 0));
        }
        return List.copyOf(orders);
    }
}
