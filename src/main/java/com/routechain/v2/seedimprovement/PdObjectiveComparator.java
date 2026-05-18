package com.routechain.v2.seedimprovement;

public final class PdObjectiveComparator {
    public boolean better(PdEvaluation candidate, PdEvaluation baseline) {
        if (candidate == null || !candidate.valid()) {
            return false;
        }
        if (baseline == null) {
            return true;
        }
        if (candidate.assignedCount() != baseline.assignedCount()) {
            return candidate.assignedCount() > baseline.assignedCount();
        }
        if (candidate.lateCount() != baseline.lateCount()) {
            return candidate.lateCount() < baseline.lateCount();
        }
        int lateness = Double.compare(candidate.totalLatenessMinutes(), baseline.totalLatenessMinutes());
        if (lateness != 0) {
            return lateness < 0;
        }
        int distance = Double.compare(candidate.distanceKm(), baseline.distanceKm());
        if (distance != 0) {
            return distance < 0;
        }
        return candidate.durationMinutes() < baseline.durationMinutes();
    }

    public boolean validNoRegression(PdEvaluation candidate, PdEvaluation baseline) {
        if (candidate == null || baseline == null || !candidate.valid()) {
            return false;
        }
        return candidate.assignedCount() >= baseline.assignedCount()
                && candidate.lateCount() <= baseline.lateCount()
                && candidate.totalLatenessMinutes() <= baseline.totalLatenessMinutes()
                && candidate.distanceKm() < baseline.distanceKm()
                && !candidate.hasHardViolation();
    }
}
