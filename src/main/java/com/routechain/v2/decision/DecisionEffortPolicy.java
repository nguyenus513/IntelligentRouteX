package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class DecisionEffortPolicy {
    private final RouteChainDispatchV2Properties.Decision decisionProperties;

    public DecisionEffortPolicy(RouteChainDispatchV2Properties.Decision decisionProperties) {
        this.decisionProperties = decisionProperties;
    }

    public EffortDecision select(DecisionStageInputV1 input) {
        DecisionEffort base = input.stageName().requestedEffort();
        if (!decisionProperties.getEffortPolicy().isDynamicEnabled()) {
            return new EffortDecision(base, "static-stage-default", List.of());
        }
        Map<String, Object> dispatchContext = input.dispatchContext();
        Map<String, Object> candidateSet = input.candidateSet();
        int candidateCount = effectiveCandidateCount(candidateSet);
        boolean weatherBad = booleanValue(dispatchContext.get("weatherBad"));
        boolean trafficBad = booleanValue(dispatchContext.get("trafficBad"));
        double supplyDemandRatio = numberValue(dispatchContext.get("supplyDemandRatio"));
        boolean scarceSupply = supplyDemandRatio > 0.0 && supplyDemandRatio < 0.9;
        boolean routeAmbiguous = numberValue(dispatchContext.get("routeAmbiguityScore")) >= 0.45;
        boolean latencyPressure = numberValue(dispatchContext.get("llmLatencyPressureMs"))
                >= decisionProperties.getEffortPolicy().getLatencyPressureThreshold().toMillis();
        int fallbackCount = listSize(dispatchContext.get("fallbackHistory"));

        List<String> reasons = new ArrayList<>();
        int complexity = candidateCount;
        if (weatherBad) {
            complexity += 2;
            reasons.add("weather-severity");
        }
        if (trafficBad) {
            complexity += 2;
            reasons.add("traffic-severity");
        }
        if (scarceSupply) {
            complexity += 1;
            reasons.add("supply-demand-imbalance");
        }
        if (routeAmbiguous) {
            complexity += 2;
            reasons.add("route-ambiguity");
        }
        if (fallbackCount > 0) {
            complexity += 1;
            reasons.add("prior-stage-fallback");
        }
        if (latencyPressure) {
            reasons.add("latency-pressure");
        }

        DecisionEffort selected = base;
        // Local 9router smoke runs are latency-bound. Keep the adaptive policy
        // as a downshift-only policy so heavy stages never exceed medium effort.
        if (base == DecisionEffort.XHIGH && latencyPressure) {
            selected = DecisionEffort.MEDIUM;
        } else if (base == DecisionEffort.HIGH && !weatherBad && !trafficBad) {
            selected = DecisionEffort.MEDIUM;
        }

        String reason = selected == base
                ? (reasons.isEmpty() ? "dynamic-stage-default" : "dynamic-hold-" + String.join("+", reasons))
                : "dynamic-adjust-" + String.join("+", reasons);
        return new EffortDecision(selected, reason, List.copyOf(reasons));
    }

    private int effectiveCandidateCount(Map<String, Object> candidateSet) {
        if (candidateSet == null) {
            return 0;
        }
        Object topIds = candidateSet.get("topIds");
        if (topIds instanceof List<?> list && !list.isEmpty()) {
            return list.size();
        }
        for (String key : List.of("proposalCount", "selectorCandidateCount", "driverCandidateCount", "anchorCount", "bundleCount", "robustUtilityCount")) {
            Object value = candidateSet.get(key);
            if (value instanceof Number number) {
                return number.intValue();
            }
        }
        return 0;
    }

    private boolean booleanValue(Object value) {
        return value instanceof Boolean bool && bool;
    }

    private double numberValue(Object value) {
        return value instanceof Number number ? number.doubleValue() : 0.0;
    }

    private int listSize(Object value) {
        return value instanceof List<?> list ? list.size() : 0;
    }

    public record EffortDecision(
            DecisionEffort requestedEffort,
            String selectionReason,
            List<String> qualityFlags) {
        public EffortDecision {
            qualityFlags = qualityFlags == null ? List.of() : List.copyOf(qualityFlags);
        }
    }
}
