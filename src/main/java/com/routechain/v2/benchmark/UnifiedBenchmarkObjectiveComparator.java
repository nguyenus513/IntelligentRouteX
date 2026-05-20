package com.routechain.v2.benchmark;

import java.util.Comparator;

public final class UnifiedBenchmarkObjectiveComparator implements Comparator<UnifiedBenchmarkObjectiveComparator.ObjectiveRow> {
    @Override
    public int compare(ObjectiveRow left, ObjectiveRow right) {
        if (left == right) return 0;
        if (left == null) return -1;
        if (right == null) return 1;
        int coverage = Double.compare(left.coverageRate(), right.coverageRate());
        if (coverage != 0) return coverage;
        int hard = Integer.compare(right.hardViolations(), left.hardViolations());
        if (hard != 0) return hard;
        int late = Integer.compare(right.lateCount(), left.lateCount());
        if (late != 0) return late;
        int lateness = Double.compare(right.totalLateness(), left.totalLateness());
        if (lateness != 0) return lateness;
        int vehicles = Integer.compare(right.vehicleCount(), left.vehicleCount());
        if (vehicles != 0) return vehicles;
        int distance = Double.compare(right.distanceKm(), left.distanceKm());
        if (distance != 0) return distance;
        return Long.compare(right.runtimeMs(), left.runtimeMs());
    }

    public boolean leftNoWorse(ObjectiveRow left, ObjectiveRow right) {
        return compare(left, right) >= 0;
    }

    public record ObjectiveRow(
            String solver,
            double coverageRate,
            int hardViolations,
            int lateCount,
            double totalLateness,
            int vehicleCount,
            double distanceKm,
            long runtimeMs) {
    }
}
