package com.routechain.v2.constraints;

import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectorCandidate;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FeasibilityOracleTest {
    private final FeasibilityOracle oracle = new FeasibilityOracle();

    @Test
    void acceptsFeasibleSelectorCandidate() {
        assertTrue(oracle.check(candidate(true, List.of())).feasible());
    }

    @Test
    void rejectsMarkedInfeasibleCandidate() {
        ConstraintCheckResult result = oracle.check(candidate(false, List.of()));

        assertFalse(result.feasible());
        assertTrue(result.violations().stream().anyMatch(violation -> violation.code().equals("candidate-marked-infeasible")));
        assertTrue(result.reasonCodes().contains("candidate-marked-infeasible"));
        assertEquals(1, result.violationCountsByCode().get("candidate-marked-infeasible"));
    }

    @Test
    void rejectsFrozenPrefixViolationForActiveRouteCandidate() {
        SelectorCandidate candidate = new SelectorCandidate(
                "selector-candidate/v1",
                "active-bad",
                "active-route-1",
                "order-a",
                "driver-a",
                List.of("order-a"),
                0.8,
                0.8,
                RouteProposalSource.ACTIVE_ROUTE_INSERTION,
                "active-route-1",
                false,
                0.8,
                true,
                List.of(),
                List.of("frozen-prefix-violation"));

        ConstraintCheckResult result = oracle.check(candidate);

        assertFalse(result.feasible());
        assertTrue(result.reasonCodes().contains("frozen-prefix-mutated"));
    }

    @Test
    void rejectsReadyTimeAndFoodOnVehicleSignals() {
        ConstraintCheckResult result = oracle.check(candidate(true, List.of(
                "active-insertion-pickup-before-ready",
                "food-on-vehicle-hard-limit")));

        assertFalse(result.feasible());
        assertTrue(result.reasonCodes().contains("pickup-before-ready-time"));
        assertTrue(result.reasonCodes().contains("food-on-vehicle-max-exceeded"));
    }

    @Test
    void rejectsCapacityExceededWithEvidence() {
        SelectorCandidate tooLarge = new SelectorCandidate(
                "selector-candidate/v1",
                "too-large",
                "bundle-large",
                "order-a",
                "driver-a",
                List.of("order-1", "order-2", "order-3", "order-4", "order-5"),
                0.8,
                0.8,
                RouteProposalSource.HEURISTIC_FAST,
                "cluster-a",
                false,
                0.8,
                true,
                List.of(),
                List.of());

        ConstraintCheckResult result = oracle.check(tooLarge);

        assertFalse(result.feasible());
        assertTrue(result.reasonCodes().contains("capacity-exceeded"));
        assertEquals(5, result.violations().stream()
                .filter(violation -> violation.code().equals("capacity-exceeded"))
                .findFirst()
                .orElseThrow()
                .evidence()
                .get("actualOrders"));
    }

    private SelectorCandidate candidate(boolean feasible, List<String> degradeReasons) {
        return new SelectorCandidate(
                "selector-candidate/v1",
                "proposal-a",
                "bundle-a",
                "order-a",
                "driver-a",
                List.of("order-a"),
                0.8,
                0.8,
                RouteProposalSource.HEURISTIC_FAST,
                "cluster-a",
                false,
                0.8,
                feasible,
                List.of(),
                degradeReasons);
    }
}
