package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ContextSelector {
    private final RouteChainDispatchV2Properties.Decision decisionProperties;

    public ContextSelector(RouteChainDispatchV2Properties.Decision decisionProperties) {
        this.decisionProperties = decisionProperties;
    }

    public ContextSelectionProfile select(DecisionStageName stageName,
                                          Map<String, Object> dispatchContext,
                                          Map<String, Object> candidateSet,
                                          List<String> upstreamRefs) {
        Map<String, Object> safeDispatchContext = dispatchContext == null ? Map.of() : dispatchContext;
        Map<String, Object> safeCandidateSet = candidateSet == null ? Map.of() : candidateSet;
        int candidateCount = intValue(
                safeCandidateSet,
                "proposalCount",
                "selectorCandidateCount",
                "driverCandidateCount",
                "anchorCount",
                "bundleCount",
                "robustUtilityCount");
        int topIdCount = listSize(safeCandidateSet.get("topIds"));
        int effectiveCount = Math.max(candidateCount, topIdCount);
        boolean trafficBad = booleanValue(safeDispatchContext.get("trafficBad"));
        boolean weatherBad = booleanValue(safeDispatchContext.get("weatherBad"));
        boolean lateHour = booleanValue(safeDispatchContext.get("lateHour"));
        boolean scarceSupply = doubleValue(safeDispatchContext.get("supplyDemandRatio")) > 0.0
                && doubleValue(safeDispatchContext.get("supplyDemandRatio")) < 0.9;
        boolean denseHotspot = effectiveCount >= decisionProperties.getContextSelection().getDenseCandidateThreshold();
        boolean compressed = effectiveCount <= decisionProperties.getContextSelection().getCompactCandidateThreshold()
                && !trafficBad
                && !weatherBad
                && !denseHotspot;

        List<String> overlays = new ArrayList<>();
        if (denseHotspot) {
            overlays.add("dense-hotspot");
        }
        if (weatherBad) {
            overlays.add("heavy-rain");
        }
        if (trafficBad) {
            overlays.add("traffic-shock");
        }
        if (scarceSupply) {
            overlays.add("scarce-supply");
        }
        if (lateHour) {
            overlays.add("late-hour");
        }

        List<String> toolFetchPlan = new ArrayList<>();
        if (decisionProperties.getContextSelection().isToolFetchEnabled()) {
            switch (stageName) {
                case PAIR_BUNDLE -> toolFetchPlan.add("get_bundle_details");
                case DRIVER -> toolFetchPlan.add("get_driver_details");
                case ROUTE_GENERATION, ROUTE_CRITIQUE -> toolFetchPlan.add("get_route_vector_summary");
                case SCENARIO -> toolFetchPlan.add("get_scenario_breakdown");
                case FINAL_SELECTION -> toolFetchPlan.add("get_conflict_summary");
                default -> {
                }
            }
        }

        List<String> qualityFlags = new ArrayList<>();
        if (compressed) {
            qualityFlags.add("context-compact");
        } else {
            qualityFlags.add("context-expanded");
        }
        if (!upstreamRefs.isEmpty()) {
            qualityFlags.add("upstream-memory-present");
        }
        if (!toolFetchPlan.isEmpty()) {
            qualityFlags.add("tool-fetch-planned");
        }

        String profileName;
        if (denseHotspot || trafficBad || weatherBad) {
            profileName = "stress-detailed";
        } else if (compressed) {
            profileName = "compact";
        } else {
            profileName = "balanced";
        }

        LinkedHashMap<String, Object> selectedContext = new LinkedHashMap<>();
        selectedContext.put("effectiveCandidateCount", effectiveCount);
        selectedContext.put("weatherBad", weatherBad);
        selectedContext.put("trafficBad", trafficBad);
        selectedContext.put("lateHour", lateHour);
        selectedContext.put("scarceSupply", scarceSupply);
        selectedContext.put("denseHotspot", denseHotspot);
        selectedContext.put("toolFetchPlan", List.copyOf(toolFetchPlan));
        selectedContext.put("upstreamRefCount", upstreamRefs == null ? 0 : upstreamRefs.size());
        selectedContext.put("dispatchDecisionMode", safeDispatchContext.getOrDefault("decisionMode", ""));

        return new ContextSelectionProfile(
                profileName,
                compressed,
                List.copyOf(overlays),
                List.copyOf(toolFetchPlan),
                List.copyOf(qualityFlags),
                "profile=%s candidates=%d overlays=%s".formatted(profileName, effectiveCount, overlays),
                Map.copyOf(selectedContext));
    }

    private int intValue(Map<String, Object> source, String... keys) {
        for (String key : keys) {
            Object value = source.get(key);
            if (value instanceof Number number) {
                return number.intValue();
            }
        }
        return 0;
    }

    private int listSize(Object value) {
        return value instanceof List<?> list ? list.size() : 0;
    }

    private boolean booleanValue(Object value) {
        return value instanceof Boolean bool && bool;
    }

    private double doubleValue(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0.0;
    }
}
