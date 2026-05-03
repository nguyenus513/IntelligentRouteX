package com.routechain.v2.benchmark;

import com.routechain.v2.bundle.BundleFamily;
import com.routechain.v2.bundle.BundlePoolSummary;

import java.util.Map;
import java.util.TreeMap;

public record DispatchBundleDiversityMetrics(
        int candidateCount,
        int retainedCount,
        int familyDiversityCount,
        int diversityRetainedCount,
        int lateRiskRescueCandidateCount,
        int activeRouteAddonCandidateCount,
        Map<String, Integer> familyGeneratedCounts,
        Map<String, Integer> familyRetainedCounts,
        Map<String, Integer> rejectedByReasonCounts) {

    public DispatchBundleDiversityMetrics {
        familyGeneratedCounts = familyGeneratedCounts == null ? Map.of() : Map.copyOf(familyGeneratedCounts);
        familyRetainedCounts = familyRetainedCounts == null ? Map.of() : Map.copyOf(familyRetainedCounts);
        rejectedByReasonCounts = rejectedByReasonCounts == null ? Map.of() : Map.copyOf(rejectedByReasonCounts);
    }

    public static DispatchBundleDiversityMetrics empty() {
        return new DispatchBundleDiversityMetrics(0, 0, 0, 0, 0, 0, Map.of(), Map.of(), Map.of());
    }

    public static DispatchBundleDiversityMetrics from(BundlePoolSummary summary) {
        if (summary == null) {
            return empty();
        }
        return new DispatchBundleDiversityMetrics(
                summary.candidateCount(),
                summary.retainedCount(),
                positiveFamilyCount(summary.familyRetainedCounts()),
                summary.diversityRetainedCount(),
                summary.lateRiskRescueCandidateCount(),
                summary.activeRouteAddonCandidateCount(),
                familyMap(summary.familyGeneratedCounts()),
                familyMap(summary.familyRetainedCounts()),
                summary.rejectedByReasonCounts());
    }

    private static int positiveFamilyCount(Map<BundleFamily, Integer> counts) {
        if (counts == null || counts.isEmpty()) {
            return 0;
        }
        return (int) counts.values().stream()
                .filter(count -> count != null && count > 0)
                .count();
    }

    private static Map<String, Integer> familyMap(Map<BundleFamily, Integer> counts) {
        if (counts == null || counts.isEmpty()) {
            return Map.of();
        }
        Map<String, Integer> mapped = new TreeMap<>();
        counts.forEach((family, count) -> {
            if (family != null && count != null && count > 0) {
                mapped.put(family.name(), count);
            }
        });
        return mapped;
    }
}
