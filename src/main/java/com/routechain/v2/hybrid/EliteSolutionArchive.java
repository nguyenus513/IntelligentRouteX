package com.routechain.v2.hybrid;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class EliteSolutionArchive {
    private final Map<CandidateSource, SolutionSeedCandidate> bestBySource = new LinkedHashMap<>();

    public void accept(SolutionSeedCandidate seed) {
        if (seed == null || !seed.hardFeasible()) {
            return;
        }
        bestBySource.merge(seed.source(), seed, this::better);
    }

    public List<SolutionSeedCandidate> seeds() {
        return bestBySource.values().stream()
                .sorted(LexicographicSolutionComparator.SLA_STRICT.reversed())
                .toList();
    }

    public Optional<SolutionSeedCandidate> best() {
        return seeds().stream().findFirst();
    }

    public Map<CandidateSource, Long> seedCountBySource() {
        Map<CandidateSource, Long> counts = new LinkedHashMap<>();
        bestBySource.keySet().forEach(source -> counts.put(source, 1L));
        return counts;
    }

    private SolutionSeedCandidate better(SolutionSeedCandidate left, SolutionSeedCandidate right) {
        return LexicographicSolutionComparator.SLA_STRICT.better(left, right);
    }

    public Optional<SolutionSeedCandidate> bestDistanceSeed() {
        return bestBySource.values().stream().min(Comparator.comparingDouble(SolutionSeedCandidate::totalDistanceKm));
    }

    public Optional<SolutionSeedCandidate> bestSlaSeed() {
        return bestBySource.values().stream()
                .min(Comparator.comparingLong(SolutionSeedCandidate::lateOrderCount)
                        .thenComparingDouble(seed -> seed.costBreakdown().latenessCost())
                        .thenComparingDouble(SolutionSeedCandidate::totalDistanceKm));
    }

    public Optional<SolutionSeedCandidate> bestLoadBalanceSeed() {
        return bestBySource.values().stream()
                .min(Comparator.comparingDouble(seed -> seed.costBreakdown().loadPenalty()));
    }

    public Optional<SolutionSeedCandidate> nativeSeed() {
        return Optional.ofNullable(bestBySource.get(CandidateSource.IRX_NATIVE));
    }

    public List<SolutionSeedCandidate> paretoSeeds() {
        Map<CandidateSource, SolutionSeedCandidate> pareto = new LinkedHashMap<>();
        best().ifPresent(seed -> pareto.put(seed.source(), seed));
        bestDistanceSeed().ifPresent(seed -> pareto.put(seed.source(), seed));
        bestSlaSeed().ifPresent(seed -> pareto.put(seed.source(), seed));
        bestLoadBalanceSeed().ifPresent(seed -> pareto.put(seed.source(), seed));
        nativeSeed().ifPresent(seed -> pareto.put(seed.source(), seed));
        return pareto.values().stream().toList();
    }
}
