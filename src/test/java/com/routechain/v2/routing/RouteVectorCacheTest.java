package com.routechain.v2.routing;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteTestFixtures;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class RouteVectorCacheTest {

    @Test
    void reusesOnlyMatchingTraceLocalSignature() {
        RouteVectorCache cache = new RouteVectorCache();
        DispatchCandidateContext context = context();
        RouteProposal proposal = proposal("proposal-a");
        RouteVectorSummary summary = new RouteVectorSummary("route-vector-summary/v1", "proposal-a", 1, 10.0, 5.0, 2.0, 0.7, 0.3, 1, 0, 0.8, 0.5, 0.1, 3.0, "90", true);

        cache.put(proposal, context, "weather:normal", "traffic:normal", summary, List.of());

        assertNotNull(cache.get(proposal("proposal-b"), context, "weather:normal", "traffic:normal"));
        assertNull(cache.get(proposal("proposal-b"), context, "weather:bad", "traffic:normal"));
        cache.markReused();
        assertEquals(1, cache.computedCount());
        assertEquals(1, cache.reusedCount());
        assertEquals(0.5, cache.hitRate());
    }

    private DispatchCandidateContext context() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        var pairClusterStage = RouteTestFixtures.pairClusterStage(properties);
        var bundleStage = RouteTestFixtures.bundleStage(properties, pairClusterStage);
        return new DispatchCandidateContext(pairClusterStage.bufferedOrderWindow().orders(), RouteTestFixtures.request().availableDrivers(), pairClusterStage, bundleStage);
    }

    private RouteProposal proposal(String proposalId) {
        return new RouteProposal("route-proposal/v1", proposalId, "bundle-1", "order-1", "driver-1", RouteProposalSource.HEURISTIC_FAST, List.of("order-1", "order-2"), 4.0, 20.0, 0.0, true, List.of(), List.of());
    }
}
