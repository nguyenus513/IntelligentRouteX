package com.routechain.v2.improvement;

public record SearchCacheStats(
        int evaluatedMoves,
        int skippedByBudget,
        int routeEvalCacheHits,
        int routeEvalCacheMisses,
        int routeEvalCacheSize,
        int moveEvalCacheHits,
        int moveEvalCacheMisses,
        int moveEvalCacheSize,
        int legCacheHits,
        int legCacheMisses,
        int legCacheSize) {

    public double routeEvalCacheHitRate() {
        return rate(routeEvalCacheHits, routeEvalCacheMisses);
    }

    public double moveEvalCacheHitRate() {
        return rate(moveEvalCacheHits, moveEvalCacheMisses);
    }

    public double legCacheHitRate() {
        return rate(legCacheHits, legCacheMisses);
    }

    private double rate(int hits, int misses) {
        int total = hits + misses;
        if (total == 0) {
            return 0.0;
        }
        return Math.round((hits / (double) total) * 100.0) / 100.0;
    }
}
