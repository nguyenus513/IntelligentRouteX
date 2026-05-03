package com.routechain.v2.selector;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteTestFixtures;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DispatchSelectorServiceTest {

    @Test
    void consumesRobustUtilitiesAndProducesSelectorOutputsWithoutExecutorState() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        var scenarioStage = RouteTestFixtures.scenarioStage(properties);
        DispatchSelectorService service = RouteTestFixtures.selectorService(properties);

        DispatchSelectorStage stage = service.evaluate(
                RouteTestFixtures.request(),
                RouteTestFixtures.etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                scenarioStage);

        assertFalse(stage.selectorCandidates().isEmpty());
        assertFalse(stage.objectiveBreakdowns().isEmpty());
        assertEquals(stage.selectorCandidates().size(), stage.objectiveBreakdowns().size());
        assertFalse(stage.trainingTraces().isEmpty());
        assertNotNull(stage.conflictGraph());
        assertNotNull(stage.globalSelectionResult());
        assertNotNull(stage.globalSelectorSummary());
    }

    @Test
    void mergesActiveInsertionCandidatesIntoSelectorPool() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        var routeCandidateStage = RouteTestFixtures.routeCandidateStage(properties);
        var routeProposalStage = RouteTestFixtures.routeProposalStage(properties);
        var scenarioStage = RouteTestFixtures.scenarioStage(properties);
        DispatchSelectorService service = RouteTestFixtures.selectorService(properties);
        ActiveRouteInsertionCandidate activeInsertion = new ActiveRouteInsertionCandidate(
                "active-route-insertion-candidate/v1",
                "active-route-1:insert:order-active:0",
                "active-route-1",
                "active-driver-1",
                "order-active",
                0,
                List.of("order-active"),
                2.0,
                8.0,
                1.0,
                0.05,
                0.05,
                0.05,
                0.96,
                true,
                List.of("active-route-regret-insertion"),
                List.of());

        DispatchSelectorStage stage = service.evaluate(
                RouteTestFixtures.request(),
                RouteTestFixtures.etaContext(),
                pairClusterStage,
                bundleStage,
                routeCandidateStage,
                routeProposalStage,
                scenarioStage,
                List.of(activeInsertion));

        assertTrue(stage.degradeReasons().contains("active-route-insertion-candidates-merged"));
        assertTrue(stage.degradeReasons().contains("active-route-bounded-alns-repair-applied"));
        assertEquals(1, stage.activeRepairTelemetry().candidateInputCount());
        assertTrue(stage.activeRepairTelemetry().candidateOutputCount() > 0);
        assertTrue(stage.activeRepairTelemetry().operatorsTried() > 0);
        assertTrue(stage.selectorCandidates().stream()
                .anyMatch(candidate -> candidate.proposalId().equals(activeInsertion.candidateId())
                        && candidate.source() == RouteProposalSource.ACTIVE_ROUTE_INSERTION
                        && candidate.reasons().contains("bounded-alns-repair-candidate")));
        assertEquals(SelectionSolverMode.MINI_EXACT, stage.globalSelectionResult().solverMode());
        assertTrue(stage.globalSelectionResult().selectedProposals().stream()
                .anyMatch(selectedProposal -> selectedProposal.proposalId().equals(activeInsertion.candidateId())));
    }
}
