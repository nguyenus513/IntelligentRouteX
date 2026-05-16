package com.routechain.v2.live;

public record LiveCyclePolicy(
        int cycleIntervalSeconds,
        int maxOrderWaitSeconds,
        int maxDeferCount,
        int mustDispatchAfterSeconds) {
    public static LiveCyclePolicy defaults() {
        return new LiveCyclePolicy(10, 60, 2, 45);
    }
}
