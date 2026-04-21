package com.routechain.v2.benchmark;

import java.util.List;

public record DispatchStagePromotionBlocker(
        String stageName,
        boolean authoritativeCandidate,
        int fallbackCount,
        int providerErrorCount,
        double routeVectorCoverage,
        boolean tokenUsagePresent,
        DispatchQualityMlAttachStatus mlAttachStatus,
        boolean readyForPromotion,
        List<String> blockerReasons) {

    public DispatchStagePromotionBlocker {
        blockerReasons = blockerReasons == null ? List.of() : List.copyOf(blockerReasons);
    }
}
