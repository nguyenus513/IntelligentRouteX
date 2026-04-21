package com.routechain.v2.benchmark;

public record DispatchQualityExecutionPolicy(
        String policyName,
        boolean sequentialCells,
        boolean isolatedOutputRoots,
        boolean artifactFlushPerCell,
        boolean windowsSafeHeavyMode,
        boolean deferredXlDefault,
        long perCellTimeoutMillis,
        long totalHarnessTimeoutMillis) {
}
