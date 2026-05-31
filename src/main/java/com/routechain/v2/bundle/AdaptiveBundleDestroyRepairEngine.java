package com.routechain.v2.bundle;

import com.routechain.v2.EtaContext;
import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.active.ActiveRouteState;
import com.routechain.v2.cluster.EtaLegCache;
import com.routechain.v2.repair.AlnsRepairEngine;
import com.routechain.v2.repair.RepairContext;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class AdaptiveBundleDestroyRepairEngine {
    private static final double DEFAULT_BREAK_RISK_THRESHOLD = 0.65;
    private final AdaptiveMlBundleDispatchLayer adaptiveLayer;
    private final ConvenientInsertionEngine insertionEngine;
    private final AlnsRepairEngine repairEngine;

    public AdaptiveBundleDestroyRepairEngine() {
        this(new AdaptiveMlBundleDispatchLayer(), new ConvenientInsertionEngine(), new AlnsRepairEngine());
    }

    public AdaptiveBundleDestroyRepairEngine(AdaptiveMlBundleDispatchLayer adaptiveLayer,
                                             ConvenientInsertionEngine insertionEngine,
                                             AlnsRepairEngine repairEngine) {
        this.adaptiveLayer = adaptiveLayer;
        this.insertionEngine = insertionEngine;
        this.repairEngine = repairEngine;
    }

    public AdaptiveBundleRepairResult repairRiskyBundles(List<BundleCandidate> selectedBundles,
                                                         BundleContext context,
                                                         EtaContext etaContext,
                                                         Instant decisionTime,
                                                         List<ActiveRouteState> activeRoutes,
                                                         EtaLegCache etaLegCache,
                                                         Duration runtimeBudget) {
        List<BundleCandidate> riskyBundles = selectedBundles == null ? List.of() : selectedBundles.stream()
                .filter(bundle -> adaptiveLayer.breakRisk(bundle, context, etaContext, decisionTime) > DEFAULT_BREAK_RISK_THRESHOLD)
                .limit(AdaptiveBundleDispatchConfig.MAX_CANDIDATE_BUNDLES)
                .toList();
        if (riskyBundles.isEmpty()) {
            return new AdaptiveBundleRepairResult(List.of(), null, Map.of(
                    "destroyRepairApplied", false,
                    "reason", "no-bundle-break-risk-above-threshold"));
        }
        List<ActiveRouteInsertionCandidate> insertionCandidates = insertionEngine.generate(
                activeRoutes,
                riskyBundles,
                context,
                decisionTime,
                etaLegCache);
        var repairResult = repairEngine.repairWithTelemetry(new RepairContext(
                activeRoutes,
                insertionCandidates.stream()
                        .limit(AdaptiveBundleDispatchConfig.MAX_INSERTION_CANDIDATES)
                        .toList(),
                boundedBudget(runtimeBudget)));
        return new AdaptiveBundleRepairResult(riskyBundles, repairResult, Map.of(
                "destroyRepairApplied", true,
                "riskyBundleCount", riskyBundles.size(),
                "operatorPolicy", "GreedRL/Adaptive operator priority -> ALNS bounded repair",
                "candidateInputCount", insertionCandidates.size(),
                "candidateOutputCount", repairResult.candidates().size(),
                "repairSuccess", !repairResult.candidates().isEmpty()));
    }

    private Duration boundedBudget(Duration requestedBudget) {
        Duration defaultBudget = Duration.ofMillis(100);
        Duration candidate = requestedBudget == null ? defaultBudget : requestedBudget;
        return candidate.compareTo(AdaptiveBundleDispatchConfig.MAX_REPAIR_BUDGET) > 0
                ? AdaptiveBundleDispatchConfig.MAX_REPAIR_BUDGET
                : candidate;
    }
}
