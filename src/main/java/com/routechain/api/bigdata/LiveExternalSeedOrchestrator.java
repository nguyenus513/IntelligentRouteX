package com.routechain.api.bigdata;

import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.external.ExternalContributorStatus;
import com.routechain.v2.external.ExternalSeedContribution;
import com.routechain.v2.external.PyvrpSeedContributor;
import com.routechain.v2.external.VroomSeedContributor;
import com.routechain.v2.hybrid.SolutionSeedCandidate;
import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.routing.MatrixSnapshotBuilder;
import com.routechain.v2.unified.DispatchMode;
import com.routechain.v2.unified.DispatchPolicy;
import com.routechain.v2.unified.DispatchStrategy;
import com.routechain.v2.unified.UnifiedDispatchRequest;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class LiveExternalSeedOrchestrator {
    private final BigDataDispatchInputMapper inputMapper;
    private final MatrixSnapshotBuilder matrixSnapshotBuilder = new MatrixSnapshotBuilder();
    private final VroomSeedContributor vroomSeedContributor = new VroomSeedContributor();
    private final PyvrpSeedContributor pyvrpSeedContributor = new PyvrpSeedContributor();

    public LiveExternalSeedOrchestrator(BigDataDispatchInputMapper inputMapper) {
        this.inputMapper = inputMapper;
    }

    public Result run(String cycleId, String regionId, List<Map<String, Object>> selected, boolean enabled, boolean required, boolean strict, int maxOrders) {
        long started = System.nanoTime();
        if (!enabled) {
            return Result.disabled(required, strict, elapsedMs(started));
        }
        List<Map<String, Object>> bounded = selected == null ? List.of() : selected.stream().limit(Math.max(1, maxOrders)).toList();
        if (bounded.isEmpty()) {
            return Result.empty(required, strict, elapsedMs(started));
        }
        try {
            DispatchV2Request dispatchRequest = inputMapper.toRequest(cycleId + ":" + regionId + ":external-seed", 0, bounded);
            UnifiedDispatchRequest unifiedRequest = new UnifiedDispatchRequest(
                    "unified-dispatch-request/v1",
                    dispatchRequest.traceId(),
                    DispatchMode.LIVE_ROLLING,
                    DispatchStrategy.CORE_PLUS_BALANCED_REPAIR,
                    dispatchRequest.openOrders(),
                    dispatchRequest.availableDrivers(),
                    dispatchRequest.regions(),
                    dispatchRequest.weatherProfile(),
                    DispatchPolicy.dashboardDefault(dispatchRequest.openOrders().size(), dispatchRequest.availableDrivers().size()),
                    dispatchRequest.decisionTime() == null ? Instant.now() : dispatchRequest.decisionTime());
            DistanceDurationMatrixSnapshot matrix = matrixSnapshotBuilder.build(
                    cycleId,
                    regionId,
                    "LIVE_EXTERNAL_SEED_SYNTHETIC",
                    matrixNodes(dispatchRequest));
            ContributionView vroom = ContributionView.from("VROOM", timedContribution(() -> vroomSeedContributor.contribute(unifiedRequest, matrix)));
            ContributionView pyvrp = ContributionView.from("PYVRP", timedContribution(() -> pyvrpSeedContributor.contribute(unifiedRequest, matrix)));
            ContributionView best = best(vroom, pyvrp);
            boolean passed = !required || (vroom.attempted() && pyvrp.attempted() && (vroom.ok() || pyvrp.ok() || !strict));
            String gap = passed ? "" : evidenceGap(vroom, pyvrp, strict);
            return new Result(true, required, strict, bounded.size(), dispatchRequest.availableDrivers().size(), elapsedMs(started), vroom, pyvrp, best, passed, gap);
        } catch (RuntimeException exception) {
            ContributionView error = ContributionView.error("LIVE_EXTERNAL_SEED", exception, elapsedMs(started));
            return new Result(true, required, strict, bounded.size(), 0, elapsedMs(started), error, error, error, !required || !strict, rootReason(exception));
        }
    }

    private List<MatrixSnapshotBuilder.MatrixNode> matrixNodes(DispatchV2Request request) {
        List<MatrixSnapshotBuilder.MatrixNode> nodes = new ArrayList<>();
        request.availableDrivers().forEach(driver -> nodes.add(new MatrixSnapshotBuilder.MatrixNode(
                "DRIVER:" + driver.driverId(), driver.currentLocation().latitude(), driver.currentLocation().longitude())));
        request.openOrders().forEach(order -> {
            nodes.add(new MatrixSnapshotBuilder.MatrixNode("PICKUP:" + order.orderId(), order.pickupPoint().latitude(), order.pickupPoint().longitude()));
            nodes.add(new MatrixSnapshotBuilder.MatrixNode("DROPOFF:" + order.orderId(), order.dropoffPoint().latitude(), order.dropoffPoint().longitude()));
        });
        return nodes;
    }

    private TimedContribution timedContribution(ContributionCall call) {
        long started = System.nanoTime();
        try {
            return new TimedContribution(call.run(), elapsedMs(started));
        } catch (RuntimeException exception) {
            ExternalSeedContribution contribution = new ExternalSeedContribution(
                    "EXTERNAL_SEED",
                    ExternalContributorStatus.ERROR,
                    null,
                    rootReason(exception),
                    Map.of("error", rootReason(exception)));
            return new TimedContribution(contribution, elapsedMs(started));
        }
    }

    private ContributionView best(ContributionView first, ContributionView second) {
        if (first.ok() && !second.ok()) return first;
        if (second.ok() && !first.ok()) return second;
        if (first.coverageRate() > second.coverageRate()) return first;
        if (second.coverageRate() > first.coverageRate()) return second;
        return first.totalDistanceKm() <= second.totalDistanceKm() ? first : second;
    }

    private String evidenceGap(ContributionView vroom, ContributionView pyvrp, boolean strict) {
        if (strict) return "strict-required-external-seed-failed:vroom=" + vroom.status() + ",pyvrp=" + pyvrp.status();
        return "required-attempt-only:vroom=" + vroom.status() + ",pyvrp=" + pyvrp.status();
    }

    private long elapsedMs(long startedNanos) {
        return Math.max(0L, (System.nanoTime() - startedNanos) / 1_000_000L);
    }

    private static String rootReason(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null) current = current.getCause();
        String message = current.getMessage();
        return current.getClass().getSimpleName() + (message == null || message.isBlank() ? "" : ":" + message);
    }

    @FunctionalInterface
    private interface ContributionCall {
        ExternalSeedContribution run();
    }

    private record TimedContribution(ExternalSeedContribution contribution, long runtimeMs) {}

    public record ContributionView(String contributor, boolean attempted, String status, boolean ok, long runtimeMs, int routeCount, double coverageRate, double totalDistanceKm, long lateCount, String reason, Map<String, Object> diagnostics) {
        static ContributionView from(String contributor, TimedContribution timed) {
            ExternalSeedContribution contribution = timed.contribution();
            SolutionSeedCandidate seed = contribution == null ? null : contribution.seed();
            String status = contribution == null || contribution.status() == null ? ExternalContributorStatus.EVIDENCE_GAP.name() : contribution.status().name();
            Map<String, Object> diagnostics = contribution == null ? Map.of() : contribution.diagnostics();
            long runtimeMs = Math.max(timed.runtimeMs(), longDiagnostic(diagnostics, "runtimeMs"));
            return new ContributionView(
                    contributor,
                    true,
                    status,
                    ExternalContributorStatus.OK.name().equals(status),
                    runtimeMs,
                    seed == null ? 0 : seed.routes().size(),
                    seed == null ? 0.0 : seed.coverageRate(),
                    seed == null ? 0.0 : seed.totalDistanceKm(),
                    seed == null ? 0L : seed.lateOrderCount(),
                    contribution == null ? "missing-contribution" : contribution.reason(),
                    diagnostics);
        }

        static ContributionView error(String contributor, Throwable throwable, long runtimeMs) {
            return new ContributionView(contributor, true, ExternalContributorStatus.ERROR.name(), false, runtimeMs, 0, 0.0, 0.0, 0L, rootReason(throwable), Map.of("error", rootReason(throwable)));
        }

        Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("contributor", contributor);
            map.put("attempted", attempted);
            map.put("status", status);
            map.put("ok", ok);
            map.put("runtimeMs", runtimeMs);
            map.put("routeCount", routeCount);
            map.put("coverageRate", Math.round(coverageRate * 1000.0) / 1000.0);
            map.put("totalDistanceKm", Math.round(totalDistanceKm * 100.0) / 100.0);
            map.put("lateCount", lateCount);
            map.put("reason", reason);
            map.put("diagnostics", diagnostics);
            return map;
        }

        private static long longDiagnostic(Map<String, Object> diagnostics, String key) {
            Object value = diagnostics == null ? null : diagnostics.get(key);
            if (value instanceof Number number) return number.longValue();
            try { return value == null ? 0L : Long.parseLong(String.valueOf(value)); } catch (NumberFormatException ignored) { return 0L; }
        }
    }

    public record Result(boolean enabled, boolean required, boolean strict, int orderCount, int driverCount, long runtimeMs, ContributionView vroom, ContributionView pyvrp, ContributionView bestExternalSeed, boolean requirementPassed, String evidenceGapReason) {
        static Result disabled(boolean required, boolean strict, long runtimeMs) {
            ContributionView disabled = new ContributionView("EXTERNAL_SEED", false, ExternalContributorStatus.DISABLED.name(), false, 0L, 0, 0.0, 0.0, 0L, "live-external-seed-disabled", Map.of());
            return new Result(false, required, strict, 0, 0, runtimeMs, disabled, disabled, disabled, !required, required ? "live-external-seed-disabled" : "");
        }

        static Result empty(boolean required, boolean strict, long runtimeMs) {
            ContributionView empty = new ContributionView("EXTERNAL_SEED", true, ExternalContributorStatus.EVIDENCE_GAP.name(), false, runtimeMs, 0, 0.0, 0.0, 0L, "empty-live-batch", Map.of());
            return new Result(true, required, strict, 0, 0, runtimeMs, empty, empty, empty, !required, required ? "empty-live-batch" : "");
        }

        public Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("enabled", enabled);
            map.put("required", required);
            map.put("strict", strict);
            map.put("orderCount", orderCount);
            map.put("driverCount", driverCount);
            map.put("runtimeMs", runtimeMs);
            map.put("vroom", vroom.asMap());
            map.put("pyvrp", pyvrp.asMap());
            map.put("bestExternalSeed", bestExternalSeed.asMap());
            map.put("requirementPassed", requirementPassed);
            map.put("evidenceGapReason", evidenceGapReason);
            return map;
        }
    }
}
