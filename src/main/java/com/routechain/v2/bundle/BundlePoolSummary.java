package com.routechain.v2.bundle;

import com.routechain.v2.SchemaVersioned;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public record BundlePoolSummary(
        String schemaVersion,
        int candidateCount,
        int retainedCount,
        Map<BundleFamily, Integer> familyCounts,
        Map<BundleProposalSource, Integer> sourceCounts,
        int maxBundleSize,
        List<String> degradeReasons,
        Map<BundleFamily, Integer> familyGeneratedCounts,
        Map<BundleFamily, Integer> familyRetainedCounts,
        Map<String, Integer> rejectedByReasonCounts,
        int diversityRetainedCount,
        int lateRiskRescueCandidateCount,
        int activeRouteAddonCandidateCount) implements SchemaVersioned {

    public BundlePoolSummary(
            String schemaVersion,
            int candidateCount,
            int retainedCount,
            Map<BundleFamily, Integer> familyCounts,
            Map<BundleProposalSource, Integer> sourceCounts,
            int maxBundleSize,
            List<String> degradeReasons) {
        this(schemaVersion,
                candidateCount,
                retainedCount,
                familyCounts,
                sourceCounts,
                maxBundleSize,
                degradeReasons,
                familyCounts,
                new EnumMap<>(BundleFamily.class),
                Map.of(),
                0,
                0,
                0);
    }

    public BundlePoolSummary {
        familyCounts = familyCounts == null ? new EnumMap<>(BundleFamily.class) : new EnumMap<>(familyCounts);
        sourceCounts = sourceCounts == null ? new EnumMap<>(BundleProposalSource.class) : new EnumMap<>(sourceCounts);
        degradeReasons = degradeReasons == null ? List.of() : List.copyOf(degradeReasons);
        familyGeneratedCounts = familyGeneratedCounts == null ? new EnumMap<>(BundleFamily.class) : new EnumMap<>(familyGeneratedCounts);
        familyRetainedCounts = familyRetainedCounts == null ? new EnumMap<>(BundleFamily.class) : new EnumMap<>(familyRetainedCounts);
        rejectedByReasonCounts = rejectedByReasonCounts == null ? Map.of() : Map.copyOf(rejectedByReasonCounts);
    }

    public static BundlePoolSummary empty() {
        return new BundlePoolSummary(
                "bundle-pool-summary/v1",
                0,
                0,
                new EnumMap<>(BundleFamily.class),
                new EnumMap<>(BundleProposalSource.class),
                0,
                List.of(),
                new EnumMap<>(BundleFamily.class),
                new EnumMap<>(BundleFamily.class),
                Map.of(),
                0,
                0,
                0);
    }
}
