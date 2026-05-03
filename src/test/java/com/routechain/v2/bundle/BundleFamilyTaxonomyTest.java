package com.routechain.v2.bundle;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

class BundleFamilyTaxonomyTest {

    @Test
    void includesFoodDispatchDiversityFamilies() {
        assertDoesNotThrow(() -> BundleFamily.valueOf("SAME_RESTAURANT"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("SAME_FOOD_COURT"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("SAME_DELIVERY_ZONE"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("CORRIDOR"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("NEIGHBORHOOD"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("ACTIVE_ROUTE_ADDON"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("LATE_RISK_RESCUE"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("HOLD_TO_BATCH"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("URGENT_SINGLE_FALLBACK"));
        assertDoesNotThrow(() -> BundleFamily.valueOf("DIVERSITY_EXPLORATION"));
    }
}
