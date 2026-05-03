package com.routechain.v2.rolling;

public enum RollingDecisionMode {
    DISPATCH_NOW,
    HOLD_SHORT,
    MICRO_BATCH,
    REOPTIMIZE_ACTIVE_ROUTE
}
