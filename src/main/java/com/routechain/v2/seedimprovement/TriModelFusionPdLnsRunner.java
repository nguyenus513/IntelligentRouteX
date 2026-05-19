package com.routechain.v2.seedimprovement;

import com.routechain.v2.mlproof.MlDecisionTrace;
import com.routechain.v2.mlproof.MlParticipationDiagnostics;
import com.routechain.v2.mlproof.MlWorkerInvocationTrace;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class TriModelFusionPdLnsRunner {
    private final PdDestroyRepairOperator operator;
    private final PdObjectiveComparator comparator;

    public TriModelFusionPdLnsRunner() {
        this(new PdDestroyRepairOperator(), new PdObjectiveComparator());
    }

    public TriModelFusionPdLnsRunner(PdDestroyRepairOperator operator, PdObjectiveComparator comparator) {
        this.operator = operator == null ? new PdDestroyRepairOperator() : operator;
        this.comparator = comparator == null ? new PdObjectiveComparator() : comparator;
    }

    public PdLnsResult run(PdSeedState seed, PdLnsMode mode, int maxRounds, int topBadOrders) {
        List<PdLnsResult> pool = new ArrayList<>();
        if (mode != PdLnsMode.TRI_MODEL_FUSION_NO_GREEDRL) {
            pool.add(runMode(seed, PdLnsMode.GREEDRL_CONTROLLER_PD_LNS, maxRounds, topBadOrders));
        }
        if (mode != PdLnsMode.TRI_MODEL_FUSION_NO_TABULAR) {
            pool.add(runMode(seed, PdLnsMode.TABULAR_WEIGHT_075, maxRounds, topBadOrders));
        }
        if (mode != PdLnsMode.TRI_MODEL_FUSION_NO_ROUTEFINDER) {
            pool.add(runMode(seed, PdLnsMode.ROUTEFINDER_ASSISTED_PD_LNS, maxRounds, topBadOrders));
        }
        pool.add(runMode(seed, PdLnsMode.POLICY_ONLY_PD_LNS, maxRounds, topBadOrders));
        PdLnsResult best = selectBestNoRegress(pool);
        return new PdLnsResult(
                best.applied(),
                best.baseSeed(),
                best.finalSeed(),
                best.baseEvaluation(),
                best.finalEvaluation(),
                best.rounds(),
                pool.stream().mapToInt(PdLnsResult::evaluatedOrders).sum(),
                pool.stream().mapToInt(PdLnsResult::evaluatedInsertions).sum(),
                pool.stream().mapToInt(PdLnsResult::feasibleInsertions).sum(),
                pool.stream().mapToInt(PdLnsResult::acceptedMutations).sum(),
                pool.stream().flatMap(result -> result.traces().stream()).toList(),
                combineDiagnostics(pool));
    }

    private PdLnsResult runMode(PdSeedState seed, PdLnsMode mode, int maxRounds, int topBadOrders) {
        return new PdDestroyRepairOperator().improve(seed, mode, maxRounds, topBadOrders);
    }

    private PdLnsResult selectBestNoRegress(List<PdLnsResult> pool) {
        PdLnsResult fallback = pool == null || pool.isEmpty() ? null : pool.getFirst();
        PdLnsResult best = fallback;
        if (pool == null) {
            return fallback;
        }
        for (PdLnsResult result : pool) {
            if (result == null || result.finalEvaluation() == null || result.baseEvaluation() == null) {
                continue;
            }
            if (!comparator.validNoRegression(result.finalEvaluation(), result.baseEvaluation())) {
                continue;
            }
            if (best == null || comparator.better(result.finalEvaluation(), best.finalEvaluation())) {
                best = result;
            }
        }
        return best == null ? fallback : best;
    }

    private MlParticipationDiagnostics combineDiagnostics(List<PdLnsResult> pool) {
        int decisionTraceCount = 0;
        int rankedMutationCount = 0;
        int acceptedMutationFromMlTopK = 0;
        int rewardUpdates = 0;
        List<MlDecisionTrace> decisions = new ArrayList<>();
        Map<String, MlWorkerInvocationTrace> workers = new LinkedHashMap<>();
        for (PdLnsResult result : pool) {
            MlParticipationDiagnostics diagnostics = result == null ? MlParticipationDiagnostics.empty() : result.mlParticipationDiagnostics();
            decisionTraceCount += diagnostics.decisionTraceCount();
            rankedMutationCount += diagnostics.rankedMutationCount();
            acceptedMutationFromMlTopK += diagnostics.acceptedMutationFromMlTopK();
            rewardUpdates += diagnostics.rewardUpdates();
            decisions.addAll(diagnostics.decisions());
            diagnostics.workerInvocations().forEach((name, trace) -> workers.merge(name, trace, this::mergeWorker));
        }
        Map<String, Object> policy = Map.of(
                "adaptiveSeedPolicy", Map.of("used", decisionTraceCount > 0, "decisionCount", decisionTraceCount, "affectedDecisionCount", acceptedMutationFromMlTopK),
                "adaptiveOperatorPolicy", Map.of("used", decisionTraceCount > 0, "selectedOperators", decisions.stream().map(MlDecisionTrace::operator).distinct().toList(), "affectedDecisionCount", acceptedMutationFromMlTopK),
                "adaptiveMovePriority", Map.of("used", rankedMutationCount > 0, "rankedMutationCount", rankedMutationCount, "acceptedMutationFromMlTopK", acceptedMutationFromMlTopK),
                "adaptiveRewardCalculator", Map.of("used", rewardUpdates > 0, "rewardUpdates", rewardUpdates, "positiveRewards", 0, "negativeRewards", 0));
        return new MlParticipationDiagnostics(decisionTraceCount, rankedMutationCount, acceptedMutationFromMlTopK, rewardUpdates, policy, workers, decisions);
    }

    private MlWorkerInvocationTrace mergeWorker(MlWorkerInvocationTrace left, MlWorkerInvocationTrace right) {
        return new MlWorkerInvocationTrace(
                left.workerName(),
                left.called() || right.called(),
                left.called() ? left.modelVersion() : right.modelVersion(),
                left.inferenceCount() + right.inferenceCount(),
                left.candidateCount() + right.candidateCount(),
                left.outputUsed() || right.outputUsed(),
                left.affectedDecisionCount() + right.affectedDecisionCount(),
                left.acceptedCandidateCount() + right.acceptedCandidateCount(),
                left.called() ? left.reason() : right.reason());
    }
}
