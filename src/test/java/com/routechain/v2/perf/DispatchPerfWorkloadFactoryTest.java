package com.routechain.v2.perf;

import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.v2.DispatchV2Request;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DispatchPerfWorkloadFactoryTest {
    @Test
    void denseBundleDemoUsesDeterministicRoadAwarePoints() {
        DispatchV2Request request = DispatchPerfWorkloadFactory.request(
                DispatchPerfBenchmarkHarness.WorkloadSize.XS,
                "trace-road-aware-generator",
                DispatchPerfWorkloadFactory.ScenarioWorldProfile.DENSE_BUNDLE_DEMO);

        assertThat(request.openOrders()).hasSize(20);
        assertThat(request.availableDrivers()).hasSize(5);
        assertThat(request.openOrders().stream().map(Order::pickupPoint).distinct()).hasSize(20);
        assertThat(request.openOrders().stream().map(Order::dropoffPoint).distinct()).hasSize(20);
        assertThat(request.availableDrivers().stream().map(Driver::currentLocation).distinct()).hasSize(5);
        assertThat(request.openOrders().get(0).pickupPoint().latitude()).isEqualTo(10.77633);
        assertThat(request.openOrders().get(0).dropoffPoint().longitude()).isEqualTo(106.70752);
    }
}
