package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteProposalPrePrunerTest {

    @Test
    void trimsDriversBeforeRouteGenerationUsingBundleBudget() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getCandidate().getRouteProposalBudget().setEnabled(true);
        DispatchCandidateContext context = context(properties);
        RouteProposalPrePruner pruner = new RouteProposalPrePruner();
        RouteProposalBudgetDecision budget = new RouteProposalBudgetDecision(true, "test", 4, 1, 1, 2, List.of());

        RouteProposalPruneResult result = pruner.pruneInputs(
                RouteTestFixtures.routeCandidateStage(properties).driverCandidates(),
                RouteTestFixtures.routeCandidateStage(properties).pickupAnchors(),
                context,
                budget);

        assertTrue(result.candidateCountAfterPrune() <= result.candidateCountBeforePrune());
        assertTrue(result.candidateCountAfterPrune() <= budget.maxTotalRouteProposals());
        assertTrue(result.driverCandidates().stream()
                .collect(Collectors.groupingBy(DriverCandidate::bundleId, Collectors.counting()))
                .values()
                .stream()
                .allMatch(count -> count <= budget.maxDriversPerBundle()));
        assertTrue(result.pickupAnchors().stream()
                .collect(Collectors.groupingBy(PickupAnchor::bundleId, Collectors.counting()))
                .values()
                .stream()
                .allMatch(count -> count <= budget.maxAnchorsPerBundle()));
        assertTrue(result.pruneReasonCounts().containsKey("driver-budget-exceeded")
                || result.pruneReasonCounts().containsKey("anchor-budget-exceeded"));
    }

    @Test
    void keepsTopAlternativesPerTupleAndRecordsPruneReason() {
        DispatchCandidateContext context = context(RouteChainDispatchV2Properties.defaults());
        RouteProposalPrePruner pruner = new RouteProposalPrePruner();
        PickupAnchor anchor = RouteTestFixtures.routeCandidateStage(RouteChainDispatchV2Properties.defaults()).pickupAnchors().getFirst();
        DriverCandidate driver = RouteTestFixtures.routeCandidateStage(RouteChainDispatchV2Properties.defaults()).driverCandidates().getFirst();
        RouteProposalTupleKey tupleKey = new RouteProposalTupleKey(driver.bundleId(), driver.anchorOrderId(), driver.driverId());
        RouteProposalBudgetDecision budget = new RouteProposalBudgetDecision(true, "test", 2, 4, 2, 2, List.of());

        RouteProposalPruneResult result = pruner.pruneCandidates(List.of(
                candidate("fast", tupleKey, anchor, driver, RouteProposalSource.HEURISTIC_FAST, 0.0),
                candidate("safe", tupleKey, anchor, driver, RouteProposalSource.HEURISTIC_SAFE, 0.0),
                candidate("fallback", tupleKey, anchor, driver, RouteProposalSource.FALLBACK_SIMPLE, 0.0)),
                context,
                budget);

        assertEquals(2, result.candidates().size());
        assertTrue(result.candidates().stream().anyMatch(candidate -> candidate.proposal().source() == RouteProposalSource.HEURISTIC_FAST));
        assertEquals(1, result.pruneReasonCounts().get("alternative-budget-exceeded"));
    }

    private RouteProposalCandidate candidate(String proposalId,
                                             RouteProposalTupleKey tupleKey,
                                             PickupAnchor anchor,
                                             DriverCandidate driver,
                                             RouteProposalSource source,
                                             double routeValue) {
        return new RouteProposalCandidate(
                new RouteProposal("route-proposal/v1", proposalId, driver.bundleId(), driver.anchorOrderId(), driver.driverId(), source, List.of(driver.anchorOrderId()), 4.0, 20.0, routeValue, true, List.of(), List.of()),
                tupleKey,
                anchor,
                driver,
                new RouteProposalTrace(tupleKey, source, RouteProposalEngine.stopOrderSignature(List.of(driver.anchorOrderId())), 0, 0, 0, 0, 0, 0, 0, 0, 0, List.of()));
    }

    private DispatchCandidateContext context(RouteChainDispatchV2Properties properties) {
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        return new DispatchCandidateContext(pairClusterStage.bufferedOrderWindow().orders(), RouteTestFixtures.request().availableDrivers(), pairClusterStage, bundleStage);
    }
}
