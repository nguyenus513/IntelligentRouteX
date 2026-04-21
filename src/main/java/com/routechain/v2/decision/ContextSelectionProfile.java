package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

public record ContextSelectionProfile(
        String profileName,
        boolean compressed,
        List<String> overlays,
        List<String> toolFetchPlan,
        List<String> qualityFlags,
        String summary,
        Map<String, Object> selectedContext) {

    public ContextSelectionProfile {
        overlays = overlays == null ? List.of() : List.copyOf(overlays);
        toolFetchPlan = toolFetchPlan == null ? List.of() : List.copyOf(toolFetchPlan);
        qualityFlags = qualityFlags == null ? List.of() : List.copyOf(qualityFlags);
        selectedContext = selectedContext == null ? Map.of() : Map.copyOf(selectedContext);
    }
}
