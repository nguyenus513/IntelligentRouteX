package com.routechain.v2.benchmark;

import com.routechain.api.DashboardController;
import com.routechain.v2.external.ExternalContributorStatus;
import com.routechain.v2.routing.CachingRoutingProvider;
import com.routechain.v2.routing.DistanceDurationMatrixSnapshot;
import com.routechain.v2.routing.MatrixSnapshotBuilder;
import com.routechain.v2.routing.RoutingProvider;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public final class BenchmarkHybridRunService {
    public DashboardController.RunVisualizationDto run(String jobId,
                                                       DashboardController.BenchmarkJobRequest request,
                                                       BenchmarkRunExecutor executor) {
        return executor.run(jobId, request);
    }

    public Map<String, Object> objectiveAwareDiagnostics(List<DashboardController.BenchmarkSolverResultDto> solverResults) {
        DashboardController.BenchmarkSolverResultDto hybrid = solverResult(solverResults, "IRX ML-Fused Hybrid");
        DashboardController.BenchmarkSolverResultDto distance = solverResult(solverResults, "Distance batching");
        DashboardController.BenchmarkSolverResultDto ortools = solverResult(solverResults, "OR-Tools");
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        String vsDistance = compareRawKm(hybrid, distance);
        String vsOrtools = compareRawKm(hybrid, ortools);
        String vsDistanceObjective = compareObjective(hybrid, distance);
        String vsOrtoolsObjective = compareObjective(hybrid, ortools);
        diagnostics.put("vsDistance", vsDistance);
        diagnostics.put("vsOrtools", vsOrtools);
        diagnostics.put("vsDistanceObjective", vsDistanceObjective);
        diagnostics.put("vsOrtoolsObjective", vsOrtoolsObjective);
        diagnostics.put("hybridLateAdjustedKm", lateAdjustedKm(hybrid));
        diagnostics.put("distanceLateAdjustedKm", lateAdjustedKm(distance));
        diagnostics.put("ortoolsLateAdjustedKm", lateAdjustedKm(ortools));
        diagnostics.put("distanceTradeoffReason", distanceTradeoffReason(hybrid, distance, vsDistance));
        diagnostics.put("distanceObjectiveSummary", singleResultSummary(vsDistanceObjective));
        diagnostics.put("ortoolsObjectiveSummary", singleResultSummary(vsOrtoolsObjective));
        diagnostics.put("rawDistanceWinThresholdPassed", "WIN".equals(vsDistance));
        diagnostics.put("objectiveDistanceWinTieThresholdPassed", isWinOrTie(vsDistanceObjective));
        diagnostics.put("objectiveOrtoolsWinTieThresholdPassed", isWinOrTie(vsOrtoolsObjective));
        diagnostics.put("objectiveAwareBenchmarkSummary", Map.of(
                "distanceObjectiveSummary", diagnostics.get("distanceObjectiveSummary"),
                "ortoolsObjectiveSummary", diagnostics.get("ortoolsObjectiveSummary"),
                "distanceTradeoffReason", diagnostics.get("distanceTradeoffReason")));
        return diagnostics;
    }

    public Map<String, Object> profileDiagnostics(BenchmarkProfile profile) {
        BenchmarkProfile safeProfile = profile == null ? BenchmarkProfile.of(BenchmarkMode.FAST_GATE) : profile;
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("benchmarkMode", safeProfile.mode().name());
        diagnostics.put("routingMode", safeProfile.routingMode());
        diagnostics.put("distanceClaimType", safeProfile.distanceClaimType());
        diagnostics.put("fastGateSynthetic", safeProfile.fastGateSynthetic());
        diagnostics.put("swapStarEnabled", safeProfile.swapStarEnabled());
        diagnostics.put("externalContributorsEnabled", safeProfile.externalContributorsEnabled());
        diagnostics.put("topKSeeds", safeProfile.topKSeeds());
        diagnostics.put("externalContributorStatus", externalContributorStatus(safeProfile));
        return diagnostics;
    }

    public Map<String, Object> benchmarkIdentity(String datasetId,
                                                  DashboardController.ScenarioGenerateRequest scenario,
                                                  String jobId,
                                                  DashboardController.RunVisualizationDto irx,
                                                  List<DashboardController.OrderDto> orders,
                                                  List<DashboardController.DriverDto> drivers,
                                                  String scenarioHash) {
        Map<String, Object> identity = new LinkedHashMap<>();
        identity.put("datasetId", datasetId == null ? "raw-m" : datasetId);
        identity.put("scenarioId", scenario.scenarioType());
        identity.put("jobId", jobId);
        identity.put("runId", irx.runId());
        identity.put("seed", jobId);
        identity.put("scenarioHash", scenarioHash);
        identity.put("orderCount", orders.size());
        identity.put("driverCount", drivers.size());
        return identity;
    }

    public Map<String, Object> matrixSnapshotDiagnostics(DistanceDurationMatrixSnapshot snapshot) {
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("cacheHit", snapshot.cacheHit());
        diagnostics.put("nodeCount", snapshot.nodeIds().size());
        diagnostics.put("buildMs", snapshot.buildMs());
        diagnostics.put("provider", snapshot.matrixProvider());
        diagnostics.put("routingMode", snapshot.routingMode());
        diagnostics.put("fallbackApplied", snapshot.fallbackApplied());
        return diagnostics;
    }

    public List<MatrixSnapshotBuilder.MatrixNode> matrixNodes(List<DashboardController.OrderDto> orders,
                                                              List<DashboardController.DriverDto> drivers) {
        List<MatrixSnapshotBuilder.MatrixNode> nodes = new java.util.ArrayList<>();
        for (DashboardController.DriverDto driver : drivers) {
            nodes.add(new MatrixSnapshotBuilder.MatrixNode("DRIVER:" + driver.driverId(), driver.lat(), driver.lng()));
        }
        for (DashboardController.OrderDto order : orders) {
            nodes.add(new MatrixSnapshotBuilder.MatrixNode("PICKUP:" + order.orderId(), order.pickupLat(), order.pickupLng()));
            nodes.add(new MatrixSnapshotBuilder.MatrixNode("DROPOFF:" + order.orderId(), order.dropoffLat(), order.dropoffLng()));
        }
        return nodes;
    }

    public Map<String, Object> coreStageTiming(DashboardController.RunVisualizationDto irx) {
        Map<String, Object> coreFunnel = objectMap(irx.diagnostics().get("coreFunnelAudit"));
        Map<String, Object> stageLatency = objectMap(coreFunnel.get("stageLatencyMs"));
        Map<String, Object> timing = new LinkedHashMap<>();
        timing.put("pairGraphMs", number(stageLatency.get("pair-graph")));
        timing.put("bundleGenerationMs", number(stageLatency.get("bundle-pool")));
        timing.put("driverShortlistMs", number(stageLatency.get("driver-shortlist/rerank")));
        timing.put("routeProposalPoolMs", number(stageLatency.get("route-proposal-pool")));
        timing.put("scenarioEvaluationMs", number(stageLatency.get("scenario-evaluation")));
        timing.put("selectorMs", number(stageLatency.get("global-selector")));
        timing.put("coverageRepairMs", number(stageLatency.get("dispatch-executor")));
        return timing;
    }

    public Map<String, Object> globalRoutingCacheDiagnostics(RoutingProvider routingProvider) {
        return globalRoutingCacheDiagnostics(routingProvider, Map.of());
    }

    public Map<String, Object> globalRoutingCacheDiagnostics(RoutingProvider routingProvider, Map<String, Object> startStats) {
        Map<String, Object> diagnostics = new LinkedHashMap<>();
        diagnostics.put("matrixProvider", routingProvider == null ? "none" : routingProvider.providerId());
        diagnostics.put("routingMode", "FAST_GATE_BOUNDED_OSRM_WITH_SYNTHETIC_FALLBACK");
        diagnostics.put("distanceSemantics", "gate-stability-metric-not-production-road-benchmark");
        diagnostics.put("globalMatrixCacheHit", false);
        diagnostics.put("matrixBuildMs", 0);
        diagnostics.put("osrmCalls", 0);
        if (routingProvider instanceof CachingRoutingProvider cachingRoutingProvider) {
            diagnostics.putAll(cachingRoutingProvider.stats());
            int requests = intValue(diagnostics.get("routeCacheRequests"));
            int misses = intValue(diagnostics.get("routeCacheMisses"));
            int startRequests = intValue(startStats.get("routeCacheRequests"));
            int startHits = intValue(startStats.get("routeCacheHits"));
            int startMisses = intValue(startStats.get("routeCacheMisses"));
            int requestDelta = Math.max(0, requests - startRequests);
            int hitDelta = Math.max(0, intValue(diagnostics.get("routeCacheHits")) - startHits);
            int missDelta = Math.max(0, misses - startMisses);
            diagnostics.put("routeCacheRequestDelta", requestDelta);
            diagnostics.put("routeCacheHitDelta", hitDelta);
            diagnostics.put("routeCacheMissDelta", missDelta);
            diagnostics.put("routeCacheHitRateDelta", requestDelta == 0 ? 0.0 : hitDelta / (double) requestDelta);
            diagnostics.put("globalMatrixCacheHit", requestDelta > 0 && missDelta == 0);
            diagnostics.put("osrmCalls", missDelta);
        }
        return diagnostics;
    }

    private Map<String, Object> externalContributorStatus(BenchmarkProfile profile) {
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("vroom", Map.of(
                "status", profile.externalContributorsEnabled() ? ExternalContributorStatus.EVIDENCE_GAP.name() : ExternalContributorStatus.DISABLED.name(),
                "reason", profile.externalContributorsEnabled() ? "vroom-runtime-not-configured" : "disabled-in-fast-gate"));
        status.put("pyvrp", Map.of(
                "status", profile.externalContributorsEnabled() ? ExternalContributorStatus.EVIDENCE_GAP.name() : ExternalContributorStatus.DISABLED.name(),
                "reason", profile.externalContributorsEnabled() ? "pyvrp-runtime-not-configured" : "disabled-in-fast-gate"));
        return status;
    }

    @FunctionalInterface
    public interface BenchmarkRunExecutor {
        DashboardController.RunVisualizationDto run(String jobId, DashboardController.BenchmarkJobRequest request);
    }

    private DashboardController.BenchmarkSolverResultDto solverResult(List<DashboardController.BenchmarkSolverResultDto> solverResults, String solverName) {
        return solverResults.stream()
                .filter(result -> solverName.equals(result.solverName()))
                .findFirst()
                .orElse(null);
    }

    private String compareRawKm(DashboardController.BenchmarkSolverResultDto left, DashboardController.BenchmarkSolverResultDto right) {
        if (left == null || right == null || left.status() != DashboardController.SolverRunStatus.COMPLETED || right.status() != DashboardController.SolverRunStatus.COMPLETED) {
            return "EVIDENCE_GAP";
        }
        if (left.totalDistanceKm() < right.totalDistanceKm()) {
            return "WIN";
        }
        if (Double.compare(left.totalDistanceKm(), right.totalDistanceKm()) == 0) {
            return "TIE";
        }
        return "LOSS";
    }

    private String compareObjective(DashboardController.BenchmarkSolverResultDto left, DashboardController.BenchmarkSolverResultDto right) {
        if (left == null || right == null || left.status() != DashboardController.SolverRunStatus.COMPLETED || right.status() != DashboardController.SolverRunStatus.COMPLETED) {
            return "EVIDENCE_GAP";
        }
        if (left.lateOrderCount() < right.lateOrderCount()) {
            return "WIN";
        }
        if (left.lateOrderCount() > right.lateOrderCount()) {
            return "LOSS";
        }
        return compareRawKm(left, right);
    }

    private double lateAdjustedKm(DashboardController.BenchmarkSolverResultDto result) {
        if (result == null || result.status() != DashboardController.SolverRunStatus.COMPLETED) {
            return 0.0;
        }
        return Math.round((result.totalDistanceKm() + result.lateOrderCount() * 25.0) * 10.0) / 10.0;
    }

    private String distanceTradeoffReason(DashboardController.BenchmarkSolverResultDto hybrid,
                                          DashboardController.BenchmarkSolverResultDto distance,
                                          String vsDistance) {
        if (hybrid == null || distance == null) {
            return "baseline-distance-unavailable";
        }
        if ("LOSS".equals(vsDistance) && distance.lateOrderCount() > hybrid.lateOrderCount()) {
            return "baseline-distance-is-shorter-but-late";
        }
        if ("LOSS".equals(vsDistance)) {
            return "baseline-distance-is-shorter-same-or-better-late";
        }
        return "irx-raw-distance-win-or-tie";
    }

    private Map<String, Object> singleResultSummary(String result) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("win", "WIN".equals(result) ? 1 : 0);
        summary.put("tie", "TIE".equals(result) ? 1 : 0);
        summary.put("loss", "LOSS".equals(result) ? 1 : 0);
        return summary;
    }

    private boolean isWinOrTie(String result) {
        return "WIN".equals(result) || "TIE".equals(result);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value) {
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : Map.of();
    }

    private long number(Object value) {
        return value instanceof Number number ? number.longValue() : 0L;
    }

    private int intValue(Object value) {
        return value instanceof Number number ? number.intValue() : 0;
    }
}
