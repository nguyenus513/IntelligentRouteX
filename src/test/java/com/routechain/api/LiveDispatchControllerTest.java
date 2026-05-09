package com.routechain.api;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2CompatibleCore;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class LiveDispatchControllerTest {

    @Test
    void health_exposes_solve_endpoint() {
        LiveDispatchController controller = controller();

        Map<String, Object> health = controller.health();

        assertThat(health.get("status")).isEqualTo("ok");
        assertThat(health.get("endpoint")).isEqualTo("/api/v1/dispatch/solve");
    }

    @Test
    void solve_maps_live_snapshot_to_dispatch_request_and_returns_contract_response() {
        LiveDispatchController controller = controller();

        ResponseEntity<LiveDispatchController.LiveDispatchSolverResponse> response = controller.solve(validSnapshot());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        LiveDispatchController.LiveDispatchSolverResponse body = response.getBody();
        assertThat(body).isNotNull();
        assertThat(body.schemaVersion()).isEqualTo("live-dispatch-solver-response/v1");
        assertThat(body.snapshotId()).isEqualTo("snapshot-1");
        assertThat(body.mode()).isEqualTo("shadow");
        assertThat(body.fallbackReason()).isEqualTo("dispatch-v2-fallback-output");
        assertThat(body.rejectedOrders()).extracting(LiveDispatchController.ApiRejectedOrder::orderId)
                .containsExactly("order-1");
        assertThat(body.diagnostics()).containsEntry("orderCount", 1);
        assertThat(body.diagnostics()).containsEntry("driverCount", 1);
    }

    @Test
    void solve_rejects_invalid_schema_with_structured_error() {
        LiveDispatchController controller = controller();
        LiveDispatchController.LiveDispatchSnapshotRequest invalid = new LiveDispatchController.LiveDispatchSnapshotRequest(
                "wrong-schema",
                "snapshot-1",
                "2026-05-04T11:30:00+07:00",
                "hcm",
                null,
                null,
                List.of("depot"),
                Map.of(),
                List.of(),
                List.of(),
                List.of(),
                List.of(List.of(0.0)),
                Map.of(),
                Map.of(),
                Map.of());

        ResponseEntity<LiveDispatchController.LiveDispatchSolverResponse> response = controller.solve(invalid);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().fallbackReason()).isEqualTo("invalid-request");
        assertThat(response.getBody().violations()).extracting(LiveDispatchController.ApiViolation::type)
                .containsExactly("request-validation");
    }

    private LiveDispatchController controller() {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.setEnabled(false);
        return new LiveDispatchController(new DispatchV2CompatibleCore(properties, null));
    }

    private LiveDispatchController.LiveDispatchSnapshotRequest validSnapshot() {
        return new LiveDispatchController.LiveDispatchSnapshotRequest(
                "live-dispatch-snapshot/v1",
                "snapshot-1",
                "2026-05-04T11:30:00+07:00",
                "hcm-district-1",
                "shadow",
                "CLEAR",
                List.of("depot", "restaurant-a", "customer-a"),
                Map.of(),
                List.of(new LiveDispatchController.LiveOrder(
                        "order-1",
                        "restaurant-a",
                        "customer-a",
                        "restaurant-a",
                        5,
                        45,
                        2,
                        1,
                        1,
                        5,
                        null,
                        null)),
                List.of(new LiveDispatchController.LiveDriver(
                        "driver-1",
                        "depot",
                        2,
                        0,
                        120,
                        List.of(),
                        0,
                        4,
                        null,
                        true,
                        null)),
                List.of(),
                List.of(
                        List.of(0.0, 8.0, 18.0),
                        List.of(8.0, 0.0, 10.0),
                        List.of(18.0, 10.0, 0.0)),
                Map.of("trafficMode", "normal"),
                Map.of("restaurant-a", 0),
                Map.of("order-1", 0.1));
    }
}
