package com.routechain.v2.benchmark;

public record BenchmarkProfile(
        BenchmarkMode mode,
        String routingMode,
        String distanceClaimType,
        boolean fastGateSynthetic,
        boolean swapStarEnabled,
        boolean externalContributorsEnabled,
        int topKSeeds) {

    public static BenchmarkProfile of(BenchmarkMode mode) {
        BenchmarkMode safeMode = mode == null ? BenchmarkMode.FAST_GATE : mode;
        if (safeMode.quality()) {
            return new BenchmarkProfile(
                    safeMode,
                    "QUALITY_ROAD_MATRIX",
                    "road-matrix-benchmark",
                    false,
                    true,
                    true,
                    4);
        }
        return new BenchmarkProfile(
                BenchmarkMode.FAST_GATE,
                "FAST_GATE_MATRIX_FIRST_SYNTHETIC",
                "gate-stability-metric-not-production-road-benchmark",
                true,
                false,
                false,
                2);
    }
}
