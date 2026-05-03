package com.routechain.v2.benchmark;

import com.routechain.v2.repair.RepairImprovementSummary;
import com.routechain.v2.repair.RepairOperatorStat;
import com.routechain.v2.repair.RepairTelemetry;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchRepairTelemetryMetricsTest {

    @Test
    void fromNullReturnsStableEmptyMetrics() {
        DispatchRepairTelemetryMetrics metrics = DispatchRepairTelemetryMetrics.from(null);

        assertEquals("DISABLED_OR_EMPTY", metrics.mode());
        assertFalse(metrics.enabled());
        assertEquals(0, metrics.runtimeMs());
        assertTrue(metrics.operatorCounts().isEmpty());
    }

    @Test
    void fromTelemetryMapsRuntimeEvidence() {
        RepairTelemetry telemetry = new RepairTelemetry(
                "repair-telemetry/v1",
                4,
                3,
                2,
                5,
                1,
                true,
                17L,
                0.42,
                List.of(
                        new RepairOperatorStat("late-risk-removal", 2, 1, 1, 0.3, 0.2),
                        new RepairOperatorStat("late-risk-removal", 1, 1, 0, 0.4, 0.4)),
                List.of("rejected-by-gate"),
                List.of("repair-budget-limited"),
                new RepairImprovementSummary(1.0, 1.42, 0.42, "candidate-1"));

        DispatchRepairTelemetryMetrics metrics = DispatchRepairTelemetryMetrics.from(telemetry);

        assertEquals("BOUNDED_ALNS", metrics.mode());
        assertTrue(metrics.enabled());
        assertTrue(metrics.timedOut());
        assertEquals(17L, metrics.runtimeMs());
        assertEquals(4, metrics.candidateInputCount());
        assertEquals(3, metrics.candidateOutputCount());
        assertEquals(2, metrics.operatorsTried());
        assertEquals(5, metrics.acceptedMoves());
        assertEquals(1, metrics.rejectedMoves());
        assertEquals(0.42, metrics.bestImprovementDelta());
        assertEquals(3, metrics.operatorCounts().get("late-risk-removal"));
        assertEquals(List.of("rejected-by-gate"), metrics.rejectionReasons());
        assertEquals(List.of("repair-budget-limited"), metrics.degradeReasons());
    }
}
