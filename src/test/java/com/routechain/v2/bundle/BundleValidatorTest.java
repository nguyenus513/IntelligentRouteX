package com.routechain.v2.bundle;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BundleValidatorTest {

    @Test
    void rejectsOversizeDuplicateAndUnsupportedBundles() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getBundle().setMaxSize(2);
        BundleValidator validator = new BundleValidator(properties);
        BundleContext context = new BundleContext(BundleTestFixtures.window().orders(), BundleTestFixtures.graph(), List.of());

        BundleCandidate candidate = new BundleCandidate(
                "bundle-candidate/v1",
                "id",
                BundleProposalSource.DETERMINISTIC_FAMILY,
                BundleFamily.COMPACT_CLIQUE,
                "cluster-001",
                false,
                List.of(),
                List.of("order-1", "order-3", "order-4"),
                "order-1|order-3|order-4",
                "order-1",
                "0:0",
                0.0,
                false,
                List.of());

        BundleCandidate validated = validator.validate(candidate, context);

        assertFalse(validated.feasible());
    }

    @Test
    void rejectsSingleOrderBundlesInNormalBundlingMode() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        BundleValidator validator = new BundleValidator(properties);
        BundleContext context = new BundleContext(BundleTestFixtures.window().orders(), BundleTestFixtures.graph(), List.of());

        BundleCandidate candidate = new BundleCandidate(
                "bundle-candidate/v1",
                "single-order",
                BundleProposalSource.DETERMINISTIC_FAMILY,
                BundleFamily.FAN_OUT_LIGHT,
                "cluster-001",
                false,
                List.of(),
                List.of("order-1"),
                "order-1",
                "order-1",
                "0:0",
                0.0,
                false,
                List.of());

        BundleCandidate validated = validator.validate(candidate, context);

        assertFalse(validated.feasible());
        assertTrue(validated.degradeReasons().contains("bundle-size-below-minimum"));
    }
}
