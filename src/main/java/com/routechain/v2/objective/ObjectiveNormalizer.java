package com.routechain.v2.objective;

public final class ObjectiveNormalizer {
    private static final double EPSILON = 1e-9;

    public double normalize(double value, double baselineMedian, double baselineIqr) {
        return (value - baselineMedian) / Math.max(EPSILON, baselineIqr);
    }

    public double clamp01(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            return 0.0;
        }
        return Math.max(0.0, Math.min(1.0, value));
    }
}
