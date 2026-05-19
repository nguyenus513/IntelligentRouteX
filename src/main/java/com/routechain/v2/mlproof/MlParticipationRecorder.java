package com.routechain.v2.mlproof;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class MlParticipationRecorder {
    private final AtomicInteger nextDecision = new AtomicInteger(1);
    private final List<MlDecisionTrace> decisions = new ArrayList<>();
    private int rankedMutationCount;
    private int acceptedMutationFromMlTopK;
    private int rewardUpdates;
    private int positiveRewards;
    private int negativeRewards;
    private int tabularInferenceCount;
    private int tabularCandidateCount;
    private int tabularAffectedDecisionCount;
    private int tabularAcceptedCandidateCount;
    private int routefinderInferenceCount;
    private int routefinderCandidateCount;
    private int routefinderAffectedDecisionCount;
    private int routefinderAcceptedCandidateCount;

    public void recordTabularScoring(int candidateCount, boolean affectedDecision, boolean acceptedCandidate) {
        tabularInferenceCount++;
        tabularCandidateCount += Math.max(0, candidateCount);
        if (affectedDecision) {
            tabularAffectedDecisionCount++;
        }
        if (acceptedCandidate) {
            tabularAcceptedCandidateCount++;
        }
    }

    public void recordRoutefinderCandidates(int candidateCount, boolean affectedDecision, boolean acceptedCandidate) {
        routefinderInferenceCount++;
        routefinderCandidateCount += Math.max(0, candidateCount);
        if (affectedDecision) {
            routefinderAffectedDecisionCount++;
        }
        if (acceptedCandidate) {
            routefinderAcceptedCandidateCount++;
        }
    }

    public void recordDecision(String decisionType,
                               String operator,
                               int candidateCountBeforeMl,
                               int candidateCountAfterMl,
                               List<String> selectedOrderIds,
                               String selectionSource,
                               int mlRank,
                               int heuristicRank,
                               boolean accepted,
                               double gainKm,
                               double reward) {
        decisions.add(new MlDecisionTrace(
                "MLD-" + String.format("%05d", nextDecision.getAndIncrement()),
                decisionType,
                operator,
                Math.max(0, candidateCountBeforeMl),
                Math.max(0, candidateCountAfterMl),
                selectedOrderIds,
                selectionSource,
                Math.max(0, mlRank),
                Math.max(0, heuristicRank),
                accepted,
                round(gainKm)));
        rankedMutationCount += Math.max(0, candidateCountBeforeMl);
        rewardUpdates++;
        if (reward > 0.0) {
            positiveRewards++;
        } else {
            negativeRewards++;
        }
        if (accepted && mlRank > 0 && mlRank <= 5) {
            acceptedMutationFromMlTopK++;
        }
    }

    public MlParticipationDiagnostics diagnostics() {
        Map<String, Object> policy = new LinkedHashMap<>();
        policy.put("adaptiveSeedPolicy", Map.of("used", !decisions.isEmpty(), "decisionCount", Math.min(1, decisions.size()), "affectedDecisionCount", acceptedMutationFromMlTopK > 0 ? 1 : 0));
        policy.put("adaptiveOperatorPolicy", Map.of("used", !decisions.isEmpty(), "selectedOperators", decisions.stream().map(MlDecisionTrace::operator).distinct().toList(), "affectedDecisionCount", acceptedMutationFromMlTopK));
        policy.put("adaptiveMovePriority", Map.of("used", rankedMutationCount > 0, "rankedMutationCount", rankedMutationCount, "acceptedMutationFromMlTopK", acceptedMutationFromMlTopK));
        policy.put("adaptiveRewardCalculator", Map.of("used", rewardUpdates > 0, "rewardUpdates", rewardUpdates, "positiveRewards", positiveRewards, "negativeRewards", negativeRewards));
        Map<String, MlWorkerInvocationTrace> workers = new LinkedHashMap<>();
        workers.put("routefinder", new MlWorkerInvocationTrace("routefinder", routefinderInferenceCount > 0, routefinderInferenceCount > 0 ? "routefinder-candidate-provider-v0.9.10B" : "not-wired-static-v0.9.10A", routefinderInferenceCount, routefinderCandidateCount, routefinderAffectedDecisionCount > 0 || routefinderAcceptedCandidateCount > 0, routefinderAffectedDecisionCount, routefinderAcceptedCandidateCount, routefinderInferenceCount > 0 ? "route/sequence candidate provider hot path" : "not in PD-LNS hot path"));
        workers.put("tabular", new MlWorkerInvocationTrace("tabular", tabularInferenceCount > 0, tabularInferenceCount > 0 ? "tabular-mutation-scorer-v0.9.10B" : "not-wired-static-v0.9.10A", tabularInferenceCount, tabularCandidateCount, tabularAffectedDecisionCount > 0 || tabularAcceptedCandidateCount > 0, tabularAffectedDecisionCount, tabularAcceptedCandidateCount, tabularInferenceCount > 0 ? "mutation scorer hot path" : "not in PD-LNS hot path"));
        workers.put("greedrl", new MlWorkerInvocationTrace("greedrl", false, "experimental", 0, 0, false, 0, 0, "not proven in static seed improvement"));
        workers.put("forecast", new MlWorkerInvocationTrace("forecast", false, "live-rescue-only", 0, 0, false, 0, 0, "live rescue only"));
        return new MlParticipationDiagnostics(decisions.size(), rankedMutationCount, acceptedMutationFromMlTopK, rewardUpdates, policy, workers, decisions);
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
