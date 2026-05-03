package com.routechain.v2.benchmark;

import com.routechain.v2.objective.ObjectiveBreakdown;
import com.routechain.v2.objective.UnifiedObjective;
import com.routechain.v2.selector.GlobalSelectionResult;
import com.routechain.v2.selector.SelectorCandidate;
import com.routechain.v2.selector.SelectedProposal;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public record DispatchObjectiveTelemetryMetrics(
        int breakdownCount,
        double selectedTotalUtility,
        double selectedQualityCost,
        double selectedRiskCost,
        double selectedRuntimeCost,
        double selectedReward,
        List<String> selectedTopReasons) {

    public DispatchObjectiveTelemetryMetrics {
        selectedTopReasons = selectedTopReasons == null ? List.of() : List.copyOf(selectedTopReasons);
    }

    public static DispatchObjectiveTelemetryMetrics empty() {
        return new DispatchObjectiveTelemetryMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, List.of());
    }

    public static DispatchObjectiveTelemetryMetrics from(List<SelectorCandidate> candidates,
                                                         GlobalSelectionResult selectionResult) {
        if (candidates == null || candidates.isEmpty() || selectionResult == null) {
            return empty();
        }
        UnifiedObjective objective = new UnifiedObjective();
        Map<String, SelectorCandidate> byProposalId = candidates.stream()
                .collect(Collectors.toMap(SelectorCandidate::proposalId, Function.identity(), (left, right) -> left));
        List<ObjectiveBreakdown> selectedBreakdowns = selectionResult.selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .map(byProposalId::get)
                .filter(candidate -> candidate != null)
                .map(objective::scoreSelectorCandidate)
                .toList();
        return new DispatchObjectiveTelemetryMetrics(
                candidates.size(),
                selectedBreakdowns.stream().mapToDouble(ObjectiveBreakdown::totalUtility).sum(),
                selectedBreakdowns.stream().mapToDouble(ObjectiveBreakdown::qualityCost).sum(),
                selectedBreakdowns.stream().mapToDouble(ObjectiveBreakdown::riskCost).sum(),
                selectedBreakdowns.stream().mapToDouble(ObjectiveBreakdown::runtimeCost).sum(),
                selectedBreakdowns.stream().mapToDouble(ObjectiveBreakdown::rewardValue).sum(),
                selectedBreakdowns.stream()
                        .flatMap(breakdown -> breakdown.reasons().stream())
                        .distinct()
                        .limit(8)
                        .toList());
    }
}
