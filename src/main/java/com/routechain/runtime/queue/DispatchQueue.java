package com.routechain.runtime.queue;

import java.util.List;
import java.util.Map;

public interface DispatchQueue {
    void enqueue(DispatchJobEnvelope envelope);
    List<DispatchJobEnvelope> drainPriorityOrder();
    Map<QueueLane, Integer> depthByLane();
}
