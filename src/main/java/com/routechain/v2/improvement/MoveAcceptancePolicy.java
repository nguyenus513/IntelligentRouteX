package com.routechain.v2.improvement;

public final class MoveAcceptancePolicy {
    public boolean accept(boolean feasibleMode,
                          double oldKm,
                          double newKm,
                          long oldLateCount,
                          long newLateCount,
                          double oldTotalLateness,
                          double newTotalLateness) {
        if (newLateCount < 0 || newKm <= 0.0) {
            return false;
        }
        if (feasibleMode) {
            return newLateCount == 0 && newKm + 0.05 < oldKm;
        }
        if (newLateCount < oldLateCount) {
            return true;
        }
        if (newLateCount == oldLateCount && newTotalLateness + 0.05 < oldTotalLateness) {
            return true;
        }
        return newLateCount == oldLateCount && newTotalLateness <= oldTotalLateness + 0.05 && newKm + 0.05 < oldKm;
    }
}
