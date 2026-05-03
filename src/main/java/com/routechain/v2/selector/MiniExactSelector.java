package com.routechain.v2.selector;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class MiniExactSelector {
    private static final int MAX_CANDIDATES = 28;
    private static final long TIMEOUT_NANOS = 20_000_000L;

    public SelectorSelectionOutcome select(List<SelectorCandidateEnvelope> candidateEnvelopes,
                                           ConflictGraph conflictGraph) {
        List<SelectorCandidateEnvelope> feasible = candidateEnvelopes.stream()
                .filter(envelope -> envelope.candidate().feasible())
                .sorted(miniExactComparator())
                .limit(MAX_CANDIDATES)
                .toList();
        if (feasible.isEmpty()) {
            return empty(candidateEnvelopes.size(), List.of("mini-exact-no-feasible-candidates"));
        }
        Map<String, Set<String>> adjacency = adjacency(conflictGraph);
        List<SelectorCandidateEnvelope> greedyIncumbent = greedyIncumbent(feasible, adjacency);
        SearchState state = new SearchState(
                System.nanoTime(),
                greedyIncumbent,
                objectiveValue(greedyIncumbent));
        search(feasible, adjacency, 0, new ArrayList<>(), 0.0, state);
        List<SelectorCandidateEnvelope> selected = state.bestSelection().stream()
                .sorted(SelectorCandidateRanking.comparator())
                .toList();
        List<SelectedProposal> selectedProposals = SelectorCandidateRanking.toSelectedProposals(
                selected,
                proposalId -> List.of("selected-by-mini-exact-selector"));
        List<String> degradeReasons = new ArrayList<>();
        degradeReasons.add("mini-exact-selector-applied");
        if (state.timedOut()) {
            degradeReasons.add("mini-exact-selector-timeout-best-effort");
        }
        if (candidateEnvelopes.size() > MAX_CANDIDATES) {
            degradeReasons.add("mini-exact-candidate-cap-applied");
        }
        return new SelectorSelectionOutcome(
                new GlobalSelectionResult(
                        "global-selection-result/v1",
                        selectedProposals,
                        candidateEnvelopes.size(),
                        selectedProposals.size(),
                        SelectionSolverMode.MINI_EXACT,
                        SelectorCandidateRanking.objectiveValue(selected),
                        degradeReasons.stream().distinct().toList()),
                SelectorDecisionTrace.empty());
    }

    public boolean shouldUse(List<SelectorCandidateEnvelope> candidateEnvelopes) {
        return candidateEnvelopes.stream()
                .anyMatch(envelope -> envelope.candidate().source() == com.routechain.v2.route.RouteProposalSource.ACTIVE_ROUTE_INSERTION);
    }

    private Comparator<SelectorCandidateEnvelope> miniExactComparator() {
        return Comparator
                .comparing((SelectorCandidateEnvelope envelope) -> envelope.candidate().source() != com.routechain.v2.route.RouteProposalSource.ACTIVE_ROUTE_INSERTION)
                .thenComparing(SelectorCandidateRanking.comparator());
    }

    private void search(List<SelectorCandidateEnvelope> candidates,
                        Map<String, Set<String>> adjacency,
                        int index,
                        List<SelectorCandidateEnvelope> current,
                        double currentScore,
                        SearchState state) {
        if (System.nanoTime() - state.startedAt() > TIMEOUT_NANOS) {
            state.markTimedOut();
            return;
        }
        if (index >= candidates.size()) {
            state.acceptIfBetter(current, currentScore);
            return;
        }
        double optimisticBound = currentScore + candidates.subList(index, candidates.size()).stream()
                .mapToDouble(this::candidateObjective)
                .filter(score -> score > 0.0)
                .sum();
        if (optimisticBound < state.bestScore()) {
            return;
        }
        SelectorCandidateEnvelope candidate = candidates.get(index);
        if (!conflicts(candidate, current, adjacency)) {
            current.add(candidate);
            search(candidates, adjacency, index + 1, current, currentScore + candidateObjective(candidate), state);
            current.removeLast();
        }
        search(candidates, adjacency, index + 1, current, currentScore, state);
    }

    private boolean conflicts(SelectorCandidateEnvelope candidate,
                              List<SelectorCandidateEnvelope> selected,
                              Map<String, Set<String>> adjacency) {
        String proposalId = candidate.candidate().proposalId();
        return selected.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .map(SelectorCandidate::proposalId)
                .anyMatch(selectedProposalId -> adjacency.getOrDefault(proposalId, Set.of()).contains(selectedProposalId));
    }

    private List<SelectorCandidateEnvelope> greedyIncumbent(List<SelectorCandidateEnvelope> candidates,
                                                            Map<String, Set<String>> adjacency) {
        ArrayList<SelectorCandidateEnvelope> selected = new ArrayList<>();
        for (SelectorCandidateEnvelope candidate : candidates) {
            if (!conflicts(candidate, selected, adjacency)) {
                selected.add(candidate);
            }
        }
        return List.copyOf(selected);
    }

    private double objectiveValue(List<SelectorCandidateEnvelope> selected) {
        return selected.stream().mapToDouble(this::candidateObjective).sum();
    }

    private double candidateObjective(SelectorCandidateEnvelope envelope) {
        SelectorCandidate candidate = envelope.candidate();
        return SelectorCandidateRanking.objectiveUtility(candidate);
    }

    private Map<String, Set<String>> adjacency(ConflictGraph conflictGraph) {
        Map<String, Set<String>> adjacency = new HashMap<>();
        for (ConflictEdge edge : conflictGraph.edges()) {
            adjacency.computeIfAbsent(edge.leftProposalId(), ignored -> new HashSet<>()).add(edge.rightProposalId());
            adjacency.computeIfAbsent(edge.rightProposalId(), ignored -> new HashSet<>()).add(edge.leftProposalId());
        }
        return adjacency;
    }

    private SelectorSelectionOutcome empty(int retainedCandidateCount, List<String> degradeReasons) {
        return new SelectorSelectionOutcome(
                new GlobalSelectionResult(
                        "global-selection-result/v1",
                        List.of(),
                        retainedCandidateCount,
                        0,
                        SelectionSolverMode.MINI_EXACT,
                        0.0,
                        degradeReasons),
                SelectorDecisionTrace.empty());
    }

    private static final class SearchState {
        private final long startedAt;
        private List<SelectorCandidateEnvelope> bestSelection;
        private double bestScore;
        private boolean timedOut;

        private SearchState(long startedAt, List<SelectorCandidateEnvelope> bestSelection, double bestScore) {
            this.startedAt = startedAt;
            this.bestSelection = bestSelection;
            this.bestScore = bestScore;
        }

        private long startedAt() {
            return startedAt;
        }

        private List<SelectorCandidateEnvelope> bestSelection() {
            return bestSelection;
        }

        private double bestScore() {
            return bestScore;
        }

        private boolean timedOut() {
            return timedOut;
        }

        private void markTimedOut() {
            timedOut = true;
        }

        private void acceptIfBetter(List<SelectorCandidateEnvelope> current, double currentScore) {
            if (currentScore > bestScore || currentScore == bestScore && tieBreak(current) > tieBreak(bestSelection)) {
                bestScore = currentScore;
                bestSelection = List.copyOf(current);
            }
        }

        private double tieBreak(List<SelectorCandidateEnvelope> selection) {
            return selection.stream()
                    .sorted(Comparator.comparing(envelope -> envelope.candidate().proposalId()))
                    .map(SelectorCandidateEnvelope::candidate)
                    .mapToDouble(candidate -> candidate.robustUtility() + 0.01 * candidate.orderIds().size())
                    .sum();
        }
    }
}
