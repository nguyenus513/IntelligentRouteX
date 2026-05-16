package com.routechain.v2.unified;

import com.routechain.v2.hybrid.BaselineDominanceGuard;
import com.routechain.v2.hybrid.BaselineDominanceResult;
import com.routechain.v2.hybrid.DistanceCostFunction;
import com.routechain.v2.hybrid.EliteMultiStartImprover;
import com.routechain.v2.hybrid.EliteSolutionArchive;
import com.routechain.v2.hybrid.ImprovedSolutionCandidate;
import com.routechain.v2.hybrid.LexicographicSolutionComparator;
import com.routechain.v2.hybrid.SeedRouteBinding;
import com.routechain.v2.hybrid.SolutionSeedCandidate;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public final class UnifiedHybridDispatchService {
    private final EliteMultiStartImprover improver = new EliteMultiStartImprover();
    private final BaselineDominanceGuard dominanceGuard = new BaselineDominanceGuard();

    public HybridRunResult run(EliteSolutionArchive archive,
                               List<SeedRouteBinding> routeBindings,
                               SolutionSeedCandidate nativeSeed,
                               DistanceCostFunction distanceCost,
                               int topK) {
        List<ImprovedSolutionCandidate> improvedSeeds = improver.improve(routeBindings, topK, distanceCost);
        if (improvedSeeds.isEmpty()) {
            improvedSeeds = improver.improve(archive, topK);
        }
        SolutionSeedCandidate bestImprovedSeed = improvedSeeds.stream()
                .map(ImprovedSolutionCandidate::improvedSeed)
                .max(LexicographicSolutionComparator.SLA_STRICT)
                .orElse(nativeSeed);
        SolutionSeedCandidate finalSeed = betterSeed(bestImprovedSeed, nativeSeed);
        BaselineDominanceResult dominance = dominanceGuard.evaluate(finalSeed, archive);
        return new HybridRunResult(improvedSeeds, bestImprovedSeed, finalSeed, dominance, topK);
    }

    private SolutionSeedCandidate betterSeed(SolutionSeedCandidate candidate, SolutionSeedCandidate fallback) {
        if (candidate == null) {
            return fallback;
        }
        if (fallback == null) {
            return candidate;
        }
        return LexicographicSolutionComparator.SLA_STRICT.compare(candidate, fallback) >= 0 ? candidate : fallback;
    }

    public record HybridRunResult(
            List<ImprovedSolutionCandidate> improvedSeeds,
            SolutionSeedCandidate bestImprovedSeed,
            SolutionSeedCandidate finalSeed,
            BaselineDominanceResult dominance,
            int configuredTopK) {
    }
}
