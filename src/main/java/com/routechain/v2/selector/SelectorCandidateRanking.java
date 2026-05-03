package com.routechain.v2.selector;

import java.util.Comparator;
import java.util.List;
import java.util.function.Function;
import com.routechain.v2.objective.UnifiedObjective;

final class SelectorCandidateRanking {
    private static final UnifiedObjective OBJECTIVE = new UnifiedObjective();

    private SelectorCandidateRanking() {
    }

    static Comparator<SelectorCandidateEnvelope> comparator() {
        return Comparator
                .comparingDouble((SelectorCandidateEnvelope envelope) -> objectiveUtility(envelope.candidate())).reversed()
                .thenComparing(Comparator.comparingDouble((SelectorCandidateEnvelope envelope) -> envelope.candidate().selectionScore()).reversed())
                .thenComparing(Comparator.comparingDouble((SelectorCandidateEnvelope envelope) -> envelope.candidate().robustUtility()).reversed())
                .thenComparing(Comparator.comparingDouble((SelectorCandidateEnvelope envelope) -> envelope.candidate().routeValue()).reversed())
                .thenComparingDouble(SelectorCandidateEnvelope::projectedPickupEtaMinutes)
                .thenComparing(envelope -> envelope.candidate().proposalId());
    }

    static List<SelectedProposal> toSelectedProposals(List<SelectorCandidateEnvelope> rankedSelection,
                                                      Function<String, List<String>> reasonsByProposalId) {
        java.util.List<SelectedProposal> selectedProposals = new java.util.ArrayList<>(rankedSelection.size());
        for (int index = 0; index < rankedSelection.size(); index++) {
            SelectorCandidate selectorCandidate = rankedSelection.get(index).candidate();
            selectedProposals.add(new SelectedProposal(
                    "selected-proposal/v1",
                    selectorCandidate.proposalId(),
                    index + 1,
                    selectorCandidate.selectionScore(),
                    reasonsByProposalId.apply(selectorCandidate.proposalId())));
        }
        return List.copyOf(selectedProposals);
    }

    static double objectiveValue(List<SelectorCandidateEnvelope> rankedSelection) {
        return rankedSelection.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .mapToDouble(SelectorCandidateRanking::objectiveUtility)
                .sum();
    }

    static double objectiveUtility(SelectorCandidate candidate) {
        return OBJECTIVE.scoreSelectorCandidate(candidate).totalUtility();
    }
}
