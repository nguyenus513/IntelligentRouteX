package com.routechain.v2.bundle;

import java.time.Duration;

public final class AdaptiveBundleDispatchConfig {
    public static final int MAX_TOP_ORDERS = 120;
    public static final int MAX_CANDIDATE_BUNDLES = 300;
    public static final int MAX_BUNDLE_SIZE = 4;
    public static final int MAX_INSERTION_DRIVERS_PER_ORDER = 8;
    public static final int MAX_INSERTION_CANDIDATES = 300;
    public static final int MAX_REPAIR_ITERATIONS = 80;
    public static final Duration MAX_REPAIR_BUDGET = Duration.ofMillis(600);
    public static final boolean EARLY_STOP_ENABLED = true;
    public static final double MAX_INSERTION_INCREMENTAL_COMPLETION_MINUTES = 8.0;
    public static final double MAX_INSERTION_FRESHNESS_RISK = 0.72;
    public static final double MAX_INSERTION_CHURN_RISK = 0.45;
    public static final double MIN_DEADLINE_SLACK_MINUTES = 3.0;
    public static final long FORCE_ASSIGN_OLD_ORDER_MINUTES = 45L;

    private AdaptiveBundleDispatchConfig() {
    }
}
