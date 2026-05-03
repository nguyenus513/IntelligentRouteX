package com.routechain.v2.selector;

import com.routechain.v2.constraints.FeasibilityOracle;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class AcceptanceGate {
    private static final double MIN_TOTAL_SCORE_IMPROVEMENT_PCT = 1.0;
    private static final double EPSILON = 1e-9;

    private final FeasibilityOracle feasibilityOracle;

    public AcceptanceGate() {
        this(new FeasibilityOracle());
    }

    AcceptanceGate(FeasibilityOracle feasibilityOracle) {
        this.feasibilityOracle = feasibilityOracle;
    }

    public AcceptanceGateResult evaluate(GlobalSelectionResult incumbent,
                                         GlobalSelectionResult candidate,
                                         List<SelectorCandidateEnvelope> candidatePool) {
        if (candidate == null) {
            return new AcceptanceGateResult(false, objective(incumbent), 0.0, 0.0, List.of("acceptance-candidate-missing"));
        }
        List<String> rejectedReasons = new ArrayList<>();
        Map<String, SelectorCandidate> byProposalId = candidatePool == null
                ? Map.of()
                : candidatePool.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .collect(Collectors.toMap(SelectorCandidate::proposalId, Function.identity(), (left, right) -> left));
        Set<String> selectedProposalIds = candidate.selectedProposals().stream()
                .map(SelectedProposal::proposalId)
                .collect(Collectors.toSet());
        for (String proposalId : selectedProposalIds) {
            SelectorCandidate selectedCandidate = byProposalId.get(proposalId);
            if (selectedCandidate == null) {
                rejectedReasons.add("acceptance-selected-candidate-missing-" + proposalId);
                continue;
            }
            var check = feasibilityOracle.check(selectedCandidate);
            if (!check.feasible()) {
                check.reasonCodes().stream()
                        .map(reason -> "acceptance-hard-feasibility-violation-" + reason)
                        .forEach(rejectedReasons::add);
            }
        }

        double incumbentObjective = objective(incumbent);
        double candidateObjective = objective(candidate);
        double improvementPct = improvementPct(incumbentObjective, candidateObjective);
        if (incumbent != null && !incumbent.selectedProposals().isEmpty()
                && candidateObjective + EPSILON < incumbentObjective) {
            rejectedReasons.add("acceptance-objective-below-incumbent");
        }
        if (incumbent != null && !incumbent.selectedProposals().isEmpty()
                && improvementPct > 0.0
                && improvementPct + EPSILON < MIN_TOTAL_SCORE_IMPROVEMENT_PCT
                && candidate.selectedCount() < incumbent.selectedCount()) {
            rejectedReasons.add("acceptance-improvement-below-epsilon-with-coverage-regression");
        }
        return new AcceptanceGateResult(
                rejectedReasons.isEmpty(),
                incumbentObjective,
                candidateObjective,
                improvementPct,
                rejectedReasons.stream().distinct().toList());
    }

    private double objective(GlobalSelectionResult result) {
        return result == null ? 0.0 : result.objectiveValue();
    }

    private double improvementPct(double incumbentObjective, double candidateObjective) {
        if (Math.abs(incumbentObjective) < EPSILON) {
            return candidateObjective > 0.0 ? 100.0 : 0.0;
        }
        return ((candidateObjective - incumbentObjective) / Math.abs(incumbentObjective)) * 100.0;
    }
}
