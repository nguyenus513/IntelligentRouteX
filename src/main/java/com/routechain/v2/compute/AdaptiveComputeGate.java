package com.routechain.v2.compute;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.integration.MlWorkerMetadata;

public final class AdaptiveComputeGate {
    private final RouteChainDispatchV2Properties properties;

    public AdaptiveComputeGate(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public boolean enabled() {
        return properties.getCompute().getAdaptive().isEnabled();
    }

    public GateDecision decideGreedRl(GreedRlInputs inputs) {
        if (!enabled()) {
            return GateDecision.disabled("adaptive-compute-disabled");
        }
        GateDecision metadataDecision = validateMetadata(inputs.workerMetadata(), AdaptiveComputeDecision.ESCALATE_GREEDRL);
        if (metadataDecision != null) {
            return metadataDecision;
        }
        if (!inputs.workerReady()) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "greedrl-worker-not-ready", inputs.workerMetadata());
        }
        if (inputs.workingOrderCount() > inputs.maxOrdersPerRequest()) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "greedrl-scope-too-large", inputs.workerMetadata());
        }
        RouteChainDispatchV2Properties.Adaptive adaptive = properties.getCompute().getAdaptive();
        boolean complexEnough = inputs.workingOrderCount() >= adaptive.getGreedrlMinWorkingOrders()
                || inputs.acceptedBoundaryOrderCount() >= adaptive.getGreedrlMinAcceptedBoundaryOrders()
                || inputs.supportSpread() <= adaptive.getGreedrlSupportSpreadThreshold();
        if (!complexEnough) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "greedrl-complexity-below-threshold", inputs.workerMetadata());
        }
        return GateDecision.escalate(AdaptiveComputeDecision.ESCALATE_GREEDRL, inputs.workerMetadata());
    }

    public GateDecision decideRouteFinder(RouteFinderInputs inputs) {
        if (!enabled()) {
            return GateDecision.disabled("adaptive-compute-disabled");
        }
        GateDecision metadataDecision = validateMetadata(inputs.workerMetadata(), AdaptiveComputeDecision.ESCALATE_ROUTEFINDER);
        if (metadataDecision != null) {
            return metadataDecision;
        }
        if (!inputs.workerReady()) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "routefinder-worker-not-ready", inputs.workerMetadata());
        }
        RouteChainDispatchV2Properties.Adaptive adaptive = properties.getCompute().getAdaptive();
        boolean ambiguous = inputs.topEtaGapMinutes() >= 0.0
                && inputs.topEtaGapMinutes() <= adaptive.getRoutefinderEtaAmbiguityThresholdMinutes();
        boolean stopCountHeavy = inputs.stopCount() >= adaptive.getRoutefinderStopCountThreshold();
        boolean signalEscalation = (adaptive.isRoutefinderWeatherEscalationEnabled() && inputs.weatherBad())
                || (adaptive.isRoutefinderTrafficEscalationEnabled() && inputs.trafficBad())
                || (adaptive.isRoutefinderBoundaryCrossEscalationEnabled() && inputs.boundaryCross());
        if (!(ambiguous || stopCountHeavy || signalEscalation)) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "routefinder-ambiguity-below-threshold", inputs.workerMetadata());
        }
        if (inputs.tupleOrdinal() >= Math.max(1, adaptive.getRoutefinderMaxTuplesPerDispatch())) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "routefinder-tuple-budget-exhausted", inputs.workerMetadata());
        }
        return GateDecision.escalate(AdaptiveComputeDecision.ESCALATE_ROUTEFINDER, inputs.workerMetadata());
    }

    public GateDecision decideForecast(ForecastInputs inputs) {
        if (!enabled()) {
            return GateDecision.disabled("adaptive-compute-disabled");
        }
        if (properties.getCompute().getAdaptive().isForecastEnabledInHotPathByDefault()) {
            GateDecision metadataDecision = validateMetadata(inputs.workerMetadata(), AdaptiveComputeDecision.ESCALATE_FORECAST);
            if (metadataDecision != null) {
                return metadataDecision;
            }
            if (!inputs.workerReady()) {
                return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "forecast-worker-not-ready", inputs.workerMetadata());
            }
            return GateDecision.escalate(AdaptiveComputeDecision.ESCALATE_FORECAST, inputs.workerMetadata());
        }
        GateDecision metadataDecision = validateMetadata(inputs.workerMetadata(), AdaptiveComputeDecision.ESCALATE_FORECAST);
        if (metadataDecision != null) {
            return metadataDecision;
        }
        if (!inputs.workerReady()) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "forecast-worker-not-ready", inputs.workerMetadata());
        }
        RouteChainDispatchV2Properties.Adaptive adaptive = properties.getCompute().getAdaptive();
        boolean signalEscalation = (adaptive.isForecastWeatherEscalationEnabled() && inputs.weatherBad())
                || (adaptive.isForecastTrafficEscalationEnabled() && inputs.trafficBad());
        boolean ambiguous = inputs.topEtaGapMinutes() >= 0.0
                && inputs.topEtaGapMinutes() <= adaptive.getForecastAmbiguityThresholdMinutes();
        boolean enoughProposals = inputs.proposalCount() >= adaptive.getForecastMinProposalCount();
        if (!(signalEscalation || (ambiguous && enoughProposals))) {
            return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "forecast-hot-path-skip", inputs.workerMetadata());
        }
        return GateDecision.escalate(AdaptiveComputeDecision.ESCALATE_FORECAST, inputs.workerMetadata());
    }

    private GateDecision validateMetadata(MlWorkerMetadata metadata, AdaptiveComputeDecision decision) {
        RouteChainDispatchV2Properties.Adaptive adaptive = properties.getCompute().getAdaptive();
        if (!adaptive.isRequireWorkerDeviceAudit() || metadata == null || metadata.hasDeviceAudit()) {
            return null;
        }
        if (adaptive.isFailOpenWhenWorkerMetadataMissing()) {
            return GateDecision.escalate(decision, metadata).withReason("worker-device-audit-missing-fail-open");
        }
        return GateDecision.skip(AdaptiveComputeDecision.LLM_PLUS_TABULAR, "worker-device-audit-missing", metadata);
    }

    public record GateDecision(
            AdaptiveComputeDecision decision,
            boolean escalated,
            String reason,
            MlWorkerMetadata workerMetadata) {

        private static GateDecision disabled(String reason) {
            return new GateDecision(AdaptiveComputeDecision.LLM_PLUS_TABULAR, false, reason, MlWorkerMetadata.empty());
        }

        public static GateDecision skip(AdaptiveComputeDecision decision, String reason, MlWorkerMetadata workerMetadata) {
            return new GateDecision(decision, false, reason, workerMetadata == null ? MlWorkerMetadata.empty() : workerMetadata);
        }

        public static GateDecision escalate(AdaptiveComputeDecision decision, MlWorkerMetadata workerMetadata) {
            return new GateDecision(decision, true, "", workerMetadata == null ? MlWorkerMetadata.empty() : workerMetadata);
        }

        public GateDecision withReason(String reason) {
            return new GateDecision(decision, escalated, reason, workerMetadata);
        }
    }

    public record GreedRlInputs(
            int workingOrderCount,
            int acceptedBoundaryOrderCount,
            double supportSpread,
            int maxOrdersPerRequest,
            boolean workerReady,
            MlWorkerMetadata workerMetadata) {
    }

    public record RouteFinderInputs(
            int tupleOrdinal,
            int tupleCandidateCount,
            int stopCount,
            double topEtaGapMinutes,
            boolean weatherBad,
            boolean trafficBad,
            boolean boundaryCross,
            boolean workerReady,
            MlWorkerMetadata workerMetadata) {
    }

    public record ForecastInputs(
            int proposalCount,
            double topEtaGapMinutes,
            boolean weatherBad,
            boolean trafficBad,
            boolean workerReady,
            MlWorkerMetadata workerMetadata) {
    }
}
