package com.routechain.v2.compute;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.integration.MlWorkerMetadata;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AdaptiveComputeGateTest {

    @Test
    void forecastStaysOffHotPathForStableClearCase() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCompute().getAdaptive().setEnabled(true);
        AdaptiveComputeGate gate = new AdaptiveComputeGate(properties);

        AdaptiveComputeGate.GateDecision decision = gate.decideForecast(
                new AdaptiveComputeGate.ForecastInputs(
                        1,
                        5.0,
                        false,
                        false,
                        true,
                        auditedMetadata("cuda")));

        assertFalse(decision.escalated());
        assertEquals("forecast-hot-path-skip", decision.reason());
    }

    @Test
    void forecastEscalatesWhenWeatherSignalIsBad() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCompute().getAdaptive().setEnabled(true);
        AdaptiveComputeGate gate = new AdaptiveComputeGate(properties);

        AdaptiveComputeGate.GateDecision decision = gate.decideForecast(
                new AdaptiveComputeGate.ForecastInputs(
                        2,
                        4.0,
                        true,
                        false,
                        true,
                        auditedMetadata("cuda")));

        assertTrue(decision.escalated());
        assertEquals(AdaptiveComputeDecision.ESCALATE_FORECAST, decision.decision());
    }

    @Test
    void routeFinderSkipsWhenDeviceAuditIsMissing() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(true);
        properties.getCompute().getAdaptive().setFailOpenWhenWorkerMetadataMissing(false);
        AdaptiveComputeGate gate = new AdaptiveComputeGate(properties);

        AdaptiveComputeGate.GateDecision decision = gate.decideRouteFinder(
                new AdaptiveComputeGate.RouteFinderInputs(
                        0,
                        2,
                        3,
                        0.8,
                        false,
                        true,
                        false,
                        true,
                        new MlWorkerMetadata("routefinder-local", "v1", "sha256:routefinder", 7L)));

        assertFalse(decision.escalated());
        assertEquals("worker-device-audit-missing", decision.reason());
    }

    private MlWorkerMetadata auditedMetadata(String device) {
        return new MlWorkerMetadata(
                "worker",
                "v1",
                "sha256:test",
                5L,
                device,
                "fp16",
                2048L,
                8,
                "inductor",
                true,
                true);
    }
}
