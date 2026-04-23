package com.routechain.v2.scenario;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.LiveStageMetadata;
import com.routechain.v2.context.FreshnessMetadata;
import com.routechain.v2.integration.TestForecastClient;
import com.routechain.v2.route.RouteTestFixtures;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchScenarioServiceAdaptiveComputeTest {

    @Test
    void adaptiveGateSkipsForecastForStableClearCase() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setMlEnabled(true);
        properties.getMl().getForecast().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(false);
        properties.getCompute().getAdaptive().setForecastAmbiguityThresholdMinutes(-1.0);
        properties.getCompute().getAdaptive().setForecastMinProposalCount(99);
        TestForecastClient forecastClient = TestForecastClient.applied();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        DispatchScenarioService service = RouteTestFixtures.scenarioService(properties, forecastClient);

        DispatchScenarioStage stage = service.evaluate(
                RouteTestFixtures.request(),
                RouteTestFixtures.etaContext(),
                new FreshnessMetadata("freshness-metadata/v1", 0L, 0L, 0L, true, true, false),
                LiveStageMetadata.emptyList(),
                routeProposalStage,
                routeCandidateStage,
                bundleStage,
                pairClusterStage);

        assertEquals(0, forecastClient.invocations().size());
        assertTrue(stage.mlStageMetadata().isEmpty());
    }

    @Test
    void adaptiveGateEscalatesForecastForWeatherBadCase() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setMlEnabled(true);
        properties.getMl().getForecast().setEnabled(true);
        properties.getCompute().getAdaptive().setEnabled(true);
        properties.getCompute().getAdaptive().setRequireWorkerDeviceAudit(false);
        TestForecastClient forecastClient = TestForecastClient.applied();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        DispatchScenarioService service = RouteTestFixtures.scenarioService(properties, forecastClient);

        DispatchScenarioStage stage = service.evaluate(
                RouteTestFixtures.request(),
                RouteTestFixtures.weatherBadEtaContext(),
                new FreshnessMetadata("freshness-metadata/v1", 0L, 0L, 0L, true, true, false),
                LiveStageMetadata.emptyList(),
                routeProposalStage,
                routeCandidateStage,
                bundleStage,
                pairClusterStage);

        assertEquals(3, forecastClient.invocations().size());
        assertTrue(stage.mlStageMetadata().stream().anyMatch(metadata -> metadata.sourceModel().equals("chronos-2")));
    }
}
