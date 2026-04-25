package com.routechain.v2.selector;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class GreedyRepairSelector {
    private static final double SCARCE_ORDER_COVERAGE_BONUS = 0.32;

    public SelectorSelectionOutcome select(List<SelectorCandidateEnvelope> candidateEnvelopes,
                                           ConflictGraph conflictGraph,
                                           SelectionSolverMode solverMode,
                                           boolean repairEnabled) {
        Map<String, Set<String>> adjacency = adjacency(conflictGraph);
        List<SelectorCandidateEnvelope> feasibleCandidates = candidateEnvelopes.stream()
                .filter(envelope -> envelope.candidate().feasible())
                .toList();
        boolean scarceBundling = scarceBundling(feasibleCandidates);
        Comparator<SelectorCandidateEnvelope> selectionComparator = scarceBundling
                ? scarceBundlingComparator()
                : SelectorCandidateRanking.comparator();
        List<SelectorCandidateEnvelope> rankedCandidates = feasibleCandidates.stream()
                .sorted(selectionComparator)
                .toList();

        List<SelectorCandidateEnvelope> selected = new ArrayList<>();
        List<SelectorCandidateEnvelope> skippedByConflict = new ArrayList<>();
        Map<String, List<String>> selectionReasons = new HashMap<>();
        List<SelectorTraceEvent> conflictFilteredCandidates = new ArrayList<>();
        List<SelectorRepairSwap> repairSwapReplacements = new ArrayList<>();

        for (SelectorCandidateEnvelope candidateEnvelope : rankedCandidates) {
            List<String> conflictingSelected = conflictsWithSelected(candidateEnvelope, selected, adjacency);
            if (conflictingSelected.isEmpty()) {
                selected.add(candidateEnvelope);
                selectionReasons.put(candidateEnvelope.candidate().proposalId(), List.of(
                        scarceBundling ? "selected-by-scarce-bundling-greedy-pass" : "selected-by-greedy-pass"));
                continue;
            }
            skippedByConflict.add(candidateEnvelope);
            conflictFilteredCandidates.add(new SelectorTraceEvent(
                    candidateEnvelope.candidate().proposalId(),
                    "conflicts-with=" + String.join(",", conflictingSelected)));
        }

        if (repairEnabled) {
            for (SelectorCandidateEnvelope candidateEnvelope : skippedByConflict) {
                List<SelectorCandidateEnvelope> conflictingSelected = selected.stream()
                        .filter(selectedEnvelope -> conflicts(candidateEnvelope.candidate().proposalId(), selectedEnvelope.candidate().proposalId(), adjacency))
                        .toList();
                if (conflictingSelected.size() != 1) {
                    continue;
                }
                SelectorCandidateEnvelope displaced = conflictingSelected.get(0);
                if (selectionPriority(candidateEnvelope, scarceBundling) <= selectionPriority(displaced, scarceBundling)) {
                    continue;
                }
                boolean conflictsAfterSwap = selected.stream()
                        .filter(selectedEnvelope -> !selectedEnvelope.candidate().proposalId().equals(displaced.candidate().proposalId()))
                        .anyMatch(selectedEnvelope -> conflicts(candidateEnvelope.candidate().proposalId(), selectedEnvelope.candidate().proposalId(), adjacency));
                if (conflictsAfterSwap) {
                    continue;
                }
                selected.removeIf(selectedEnvelope -> selectedEnvelope.candidate().proposalId().equals(displaced.candidate().proposalId()));
                selected.add(candidateEnvelope);
                selectionReasons.remove(displaced.candidate().proposalId());
                selectionReasons.put(candidateEnvelope.candidate().proposalId(), List.of(
                        scarceBundling ? "selected-by-scarce-bundling-repair-swap" : "selected-by-repair-swap"));
                repairSwapReplacements.add(new SelectorRepairSwap(
                        displaced.candidate().proposalId(),
                        candidateEnvelope.candidate().proposalId(),
                        candidateEnvelope.candidate().selectionScore() - displaced.candidate().selectionScore()));
            }
        }

        List<SelectorCandidateEnvelope> rankedSelection = selected.stream()
                .sorted(SelectorCandidateRanking.comparator())
                .toList();
        List<SelectedProposal> selectedProposals = SelectorCandidateRanking.toSelectedProposals(
                rankedSelection,
                proposalId -> selectionReasons.getOrDefault(proposalId, List.of("selected")));
        double objectiveValue = SelectorCandidateRanking.objectiveValue(rankedSelection);
        return new SelectorSelectionOutcome(
                new GlobalSelectionResult(
                        "global-selection-result/v1",
                        List.copyOf(selectedProposals),
                        candidateEnvelopes.size(),
                        selectedProposals.size(),
                        solverMode,
                        objectiveValue,
                        scarceBundling ? List.of("scarce-bundling-priority-enabled") : List.of()),
                new SelectorDecisionTrace(List.of(), List.copyOf(conflictFilteredCandidates), List.copyOf(repairSwapReplacements)));
    }

    private Comparator<SelectorCandidateEnvelope> scarceBundlingComparator() {
        return Comparator
                .comparingDouble((SelectorCandidateEnvelope envelope) -> selectionPriority(envelope, true)).reversed()
                .thenComparing(Comparator.comparingInt((SelectorCandidateEnvelope envelope) -> envelope.candidate().orderIds().size()).reversed())
                .thenComparing(SelectorCandidateRanking.comparator());
    }

    private boolean scarceBundling(List<SelectorCandidateEnvelope> feasibleCandidates) {
        long driverCount = feasibleCandidates.stream()
                .map(envelope -> envelope.candidate().driverId())
                .distinct()
                .count();
        long orderCount = feasibleCandidates.stream()
                .flatMap(envelope -> envelope.candidate().orderIds().stream())
                .distinct()
                .count();
        boolean hasMultiOrderCandidate = feasibleCandidates.stream()
                .anyMatch(envelope -> envelope.candidate().orderIds().size() > 2);
        return driverCount > 0 && hasMultiOrderCandidate && ((double) orderCount / (double) driverCount) >= 2.0;
    }

    private double selectionPriority(SelectorCandidateEnvelope envelope, boolean scarceBundling) {
        int orderCount = envelope.candidate().orderIds().size();
        double coverageBonus = scarceBundling ? Math.max(0, orderCount - 2) * SCARCE_ORDER_COVERAGE_BONUS : 0.0;
        return envelope.candidate().selectionScore() + coverageBonus;
    }

    private List<String> conflictsWithSelected(SelectorCandidateEnvelope candidateEnvelope,
                                               List<SelectorCandidateEnvelope> selected,
                                               Map<String, Set<String>> adjacency) {
        return selected.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .map(SelectorCandidate::proposalId)
                .filter(selectedProposalId -> conflicts(candidateEnvelope.candidate().proposalId(), selectedProposalId, adjacency))
                .sorted()
                .toList();
    }

    private boolean conflicts(String leftProposalId, String rightProposalId, Map<String, Set<String>> adjacency) {
        return adjacency.getOrDefault(leftProposalId, Set.of()).contains(rightProposalId);
    }

    private Map<String, Set<String>> adjacency(ConflictGraph conflictGraph) {
        Map<String, Set<String>> adjacency = new HashMap<>();
        for (ConflictEdge edge : conflictGraph.edges()) {
            adjacency.computeIfAbsent(edge.leftProposalId(), ignored -> new HashSet<>()).add(edge.rightProposalId());
            adjacency.computeIfAbsent(edge.rightProposalId(), ignored -> new HashSet<>()).add(edge.leftProposalId());
        }
        return adjacency;
    }
}