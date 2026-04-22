package com.routechain.v2.harvest;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.decision.DecisionStageInputV1;
import com.routechain.v2.decision.DecisionStageName;
import com.routechain.v2.decision.DecisionStageOutputV1;
import com.routechain.v2.executor.DispatchAssignment;
import com.routechain.v2.executor.DispatchExecutionSummary;
import com.routechain.v2.executor.DispatchExecutorStage;
import com.routechain.v2.integration.ForecastResult;
import com.routechain.v2.integration.GreedRlBundleResult;
import com.routechain.v2.integration.MlWorkerMetadata;
import com.routechain.v2.integration.RouteFinderResult;
import com.routechain.v2.integration.TabularScoreResult;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.routing.LegRouteVector;
import com.routechain.v2.routing.RouteStop;
import com.routechain.v2.routing.RouteVectorSummary;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class HarvestRecorder {
    private final RouteChainDispatchV2Properties properties;
    private final HarvestRailWriter writer;
    private final HarvestRuntimeMetadataResolver metadataResolver;
    private final Set<String> manifestedRuns = java.util.Collections.synchronizedSet(new LinkedHashSet<>());

    public HarvestRecorder(RouteChainDispatchV2Properties properties,
                           HarvestRailWriter writer,
                           HarvestRuntimeMetadataResolver metadataResolver) {
        this.properties = properties;
        this.writer = writer;
        this.metadataResolver = metadataResolver;
    }

    public void recordRunManifest(DispatchV2Request request) {
        if (request == null || request.traceId() == null || !manifestedRuns.add(request.traceId())) {
            return;
        }
        HarvestRuntimeMetadata metadata = metadataResolver.resolve();
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("runId", request.traceId());
        payload.put("commitSha", metadata.commitSha());
        payload.put("machineClass", metadata.machineClass());
        payload.put("generatedAt", metadata.generatedAt());
        payload.put("authorityMode", properties.getDecision().getMode());
        payload.put("simulatorEnabled", true);
        payload.put("enabledFamilies", java.util.Arrays.stream(HarvestFamily.values()).map(HarvestFamily::directoryName).toList());
        payload.put("workerFingerprints", Map.of(
                "tabular", properties.getMl().getTabular().getBaseUrl(),
                "routefinder", properties.getMl().getRoutefinder().getBaseUrl(),
                "greedrl", properties.getMl().getGreedrl().getBaseUrl(),
                "forecast", properties.getMl().getForecast().getBaseUrl()));
        payload.put("sourceConfig", metadata.sourceConfig());
        payload.put("harvestWriterStats", writer.stats());
        write(HarvestFamily.HARVEST_RUN_MANIFEST, request.traceId(), new HarvestEventEnvelope(
                "harvest-run-manifest/v1",
                "stage",
                request.traceId(),
                request.traceId(),
                tickId(request),
                "dispatch-run",
                "run",
                request.traceId(),
                null,
                null,
                request.decisionTime(),
                null,
                payload));
    }

    public void recordDecisionStageInput(DecisionStageInputV1 input) {
        if (input == null) {
            return;
        }
        write(HarvestFamily.DECISION_STAGE_INPUT, input.runId(), new HarvestEventEnvelope(
                "bronze-stage-input/v1",
                "stage",
                input.traceId(),
                input.runId(),
                input.tickId(),
                input.stageName().wireName(),
                "stage",
                input.stageName().wireName(),
                null,
                null,
                instant(input.dispatchContext().get("decisionTime")),
                null,
                Map.of(
                        "dispatchContext", input.dispatchContext(),
                        "referenceFrame", input.referenceFrame(),
                        "comparisonPack", input.comparisonPack(),
                        "geospatialContext", input.geospatialContext(),
                        "burstContext", input.burstContext(),
                        "constraints", input.constraints(),
                        "contextSelection", input.contextSelection(),
                        "upstreamSummary", input.upstreamSummary(),
                        "objectiveWeights", input.objectiveWeights(),
                        "upstreamRefs", input.upstreamRefs())));
        int ordinal = 0;
        for (Map<String, Object> row : candidateRows(input.candidateSet())) {
            ordinal++;
            String entityId = String.valueOf(row.getOrDefault("id", ""));
            String candidateId = candidateId(input.stageName(), row);
            LinkedHashMap<String, Object> payload = new LinkedHashMap<>(row);
            payload.put("candidateOrdinal", ordinal);
            payload.put("candidateSource", row.getOrDefault("candidateSource", row.getOrDefault("family", "stage-window")));
            payload.put("selected", false);
            payload.put("retained", true);
            payload.put("pruned", false);
            write(HarvestFamily.DECISION_STAGE_INPUT, input.runId(), candidateEnvelope(input, entityId, candidateId, payload));
            writeGeospatialSideFamilies(input, entityId, candidateId, payload);
        }
    }

    public void recordDecisionStageOutput(DecisionStageInputV1 input, DecisionStageOutputV1 output) {
        if (input == null || output == null) {
            return;
        }
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("brainType", String.valueOf(output.brainType()));
        payload.put("providerModel", output.providerModel());
        payload.put("selectedIds", output.selectedIds());
        payload.put("meta", output.meta());
        payload.put("assessments", output.assessments());
        write(HarvestFamily.DECISION_STAGE_OUTPUT, input.runId(), new HarvestEventEnvelope(
                "bronze-stage-output/v1",
                "stage",
                output.traceId(),
                output.runId(),
                output.tickId(),
                output.stageName().wireName(),
                "stage",
                output.stageName().wireName(),
                null,
                null,
                instant(input.dispatchContext().get("decisionTime")),
                null,
                payload));
        Map<String, Map<String, Object>> assessmentItems = assessmentItems(output.assessments());
        int ordinal = 0;
        for (Map<String, Object> row : candidateRows(input.candidateSet())) {
            ordinal++;
            String entityId = String.valueOf(row.getOrDefault("id", ""));
            String candidateId = candidateId(output.stageName(), row);
            Map<String, Object> item = assessmentItems.getOrDefault(entityId, Map.of());
            LinkedHashMap<String, Object> candidatePayload = new LinkedHashMap<>(row);
            candidatePayload.put("candidateOrdinal", ordinal);
            candidatePayload.put("candidateSource", row.getOrDefault("candidateSource", row.getOrDefault("family", "stage-window")));
            candidatePayload.put("selected", output.selectedIds().contains(entityId));
            candidatePayload.put("retained", true);
            candidatePayload.put("pruned", false);
            candidatePayload.put("score", item.getOrDefault("score", 0.0));
            candidatePayload.put("rank", item.getOrDefault("rank", ordinal));
            candidatePayload.put("confidence", item.getOrDefault("confidence", output.meta().confidence()));
            candidatePayload.put("reasonCodes", item.getOrDefault("reasonCodes", List.of()));
            candidatePayload.put("dominanceFlags", item.getOrDefault("dominanceReasonCodes", List.of()));
            candidatePayload.put("regretEstimate", item.getOrDefault("regretToBestAlternative", 0.0));
            candidatePayload.put("routeVectorRefs", item.getOrDefault("routeVectorRefs", List.of(entityId)));
            candidatePayload.put("decisionQualityFlags", output.meta().decisionQualityFlags());
            write(HarvestFamily.DECISION_STAGE_OUTPUT, input.runId(), candidateEnvelope(input, entityId, candidateId, candidatePayload));
        }
    }

    public void recordDecisionStageJoin(DecisionStageInputV1 input,
                                        DecisionStageOutputV1 output,
                                        List<String> candidateIds,
                                        List<String> actualSelectedIds,
                                        boolean authoritativeApplied) {
        if (input == null || output == null) {
            return;
        }
        Set<String> actualSet = new LinkedHashSet<>(actualSelectedIds == null ? List.of() : actualSelectedIds);
        Set<String> selectedSet = new LinkedHashSet<>(output.selectedIds());
        int ordinal = 0;
        for (Map<String, Object> row : candidateRows(input.candidateSet())) {
            ordinal++;
            String entityId = String.valueOf(row.getOrDefault("id", ""));
            String candidateId = candidateId(output.stageName(), row);
            LinkedHashMap<String, Object> payload = new LinkedHashMap<>(row);
            boolean selected = selectedSet.contains(entityId);
            boolean downstreamChosen = actualSet.contains(entityId);
            payload.put("inputRef", "%s:%s".formatted(output.traceId(), output.stageName().wireName()));
            payload.put("outputRef", "%s:%s".formatted(output.traceId(), output.stageName().wireName()));
            payload.put("candidateUniverseCount", candidateIds == null ? 0 : candidateIds.size());
            payload.put("candidateOrdinal", ordinal);
            payload.put("selected", selected);
            payload.put("retained", selected);
            payload.put("pruned", !selected);
            payload.put("rejectReason", selected ? "" : "not-selected-by-teacher");
            payload.put("stageResultClass", selected ? "selected" : "rejected");
            payload.put("downstreamChosen", downstreamChosen);
            payload.put("authoritativeApplied", authoritativeApplied);
            payload.put("actualSelectedIds", actualSelectedIds == null ? List.of() : actualSelectedIds);
            write(HarvestFamily.DECISION_STAGE_JOIN, input.runId(), candidateEnvelope(input, entityId, candidateId, payload));
        }
    }

    public void recordRouteVector(String traceId,
                                  Instant decisionTime,
                                  RouteProposal proposal,
                                  RouteVectorSummary summary,
                                  List<LegRouteVector> legs,
                                  List<RouteStop> stops) {
        if (traceId == null || proposal == null || summary == null) {
            return;
        }
        LinkedHashMap<String, Object> summaryPayload = new LinkedHashMap<>();
        summaryPayload.put("proposalId", proposal.proposalId());
        summaryPayload.put("bundleId", proposal.bundleId());
        summaryPayload.put("driverId", proposal.driverId());
        summaryPayload.put("stopOrder", proposal.stopOrder());
        summaryPayload.put("routeDistanceMeters", summary.totalDistanceMeters());
        summaryPayload.put("routeTravelTimeSeconds", summary.totalTravelTimeSeconds());
        summaryPayload.put("routeCost", summary.routeCost());
        summaryPayload.put("turnCount", summary.turnCount());
        summaryPayload.put("congestionScore", summary.congestionScore());
        summaryPayload.put("directionSignature", summary.directionSignature());
        summaryPayload.put("pickupEta", proposal.projectedPickupEtaMinutes() * 60.0);
        summaryPayload.put("completionEta", proposal.projectedCompletionEtaMinutes() * 60.0);
        summaryPayload.put("legs", legs == null ? List.of() : legs);
        write(HarvestFamily.ROUTE_VECTOR_TRACE, traceId, new HarvestEventEnvelope(
                "route-vector-trace/v1",
                "stage",
                traceId,
                traceId,
                null,
                "route-proposal-pool",
                "proposal",
                proposal.proposalId(),
                "proposal:" + proposal.proposalId(),
                null,
                decisionTime,
                null,
                summaryPayload));
        List<RouteStop> safeStops = stops == null ? List.of() : List.copyOf(stops);
        for (int index = 0; index < safeStops.size(); index++) {
            RouteStop stop = safeStops.get(index);
            LinkedHashMap<String, Object> stopPayload = new LinkedHashMap<>();
            stopPayload.put("proposalId", proposal.proposalId());
            stopPayload.put("stopIndex", index);
            stopPayload.put("stopType", stop.stopType());
            stopPayload.put("orderId", stop.stopId());
            stopPayload.put("lat", stop.latitude());
            stopPayload.put("lng", stop.longitude());
            double readyEtaSeconds = stop.readyEtaMinutes() == null ? 0.0 : stop.readyEtaMinutes() * 60.0;
            stopPayload.put("projectedArrival", readyEtaSeconds);
            stopPayload.put("projectedDeparture", readyEtaSeconds);
            if (legs != null && index < legs.size()) {
                stopPayload.put("legDistanceMeters", legs.get(index).distanceMeters());
                stopPayload.put("legTravelTimeSeconds", legs.get(index).travelTimeSeconds());
            } else {
                stopPayload.put("legDistanceMeters", 0.0);
                stopPayload.put("legTravelTimeSeconds", 0.0);
            }
            write(HarvestFamily.ROUTE_STOP_TRACE, traceId, new HarvestEventEnvelope(
                    "route-stop-trace/v1",
                    "candidate",
                    traceId,
                    traceId,
                    null,
                    "route-proposal-pool",
                    "proposal-stop",
                    proposal.proposalId() + ":" + index,
                    "proposal:" + proposal.proposalId() + ":stop:" + index,
                    null,
                    decisionTime,
                    null,
                    stopPayload));
        }
    }

    public void recordTabularTeacher(String traceId,
                                     String stageName,
                                     String entityId,
                                     String teacherKind,
                                     Object featureVector,
                                     TabularScoreResult scoreResult) {
        if (scoreResult == null) {
            return;
        }
        LinkedHashMap<String, Object> payload = teacherPayload(stageName, entityId, scoreResult.workerMetadata(), scoreResult.applied(), scoreResult.fallbackUsed(), scoreResult.degradeReason());
        payload.put("teacherKind", teacherKind);
        payload.put("score", scoreResult.value());
        payload.put("uncertainty", scoreResult.uncertainty());
        payload.put("featureVector", featureVector);
        write(HarvestFamily.TABULAR_TEACHER_TRACE, traceId, new HarvestEventEnvelope(
                "tabular-teacher-trace/v1",
                "candidate",
                traceId,
                traceId,
                null,
                stageName,
                "teacher",
                entityId,
                entityId,
                null,
                Instant.now(),
                null,
                payload));
    }

    public void recordRouteFinderTeacher(String traceId,
                                         String entityId,
                                         String action,
                                         Object featureVector,
                                         RouteFinderResult result) {
        if (result == null) {
            return;
        }
        LinkedHashMap<String, Object> payload = teacherPayload("route-proposal-pool", entityId, result.workerMetadata(), result.applied(), result.fallbackUsed(), result.degradeReason());
        payload.put("teacherAction", action);
        payload.put("featureVector", featureVector);
        payload.put("routes", result.routes());
        write(HarvestFamily.ROUTEFINDER_TEACHER_TRACE, traceId, new HarvestEventEnvelope(
                "routefinder-teacher-trace/v1",
                "candidate",
                traceId,
                traceId,
                null,
                "route-proposal-pool",
                "teacher",
                entityId,
                entityId,
                null,
                Instant.now(),
                null,
                payload));
    }

    public void recordGreedRlTeacher(String traceId,
                                     String entityId,
                                     Object featureVector,
                                     GreedRlBundleResult result) {
        if (result == null) {
            return;
        }
        LinkedHashMap<String, Object> payload = teacherPayload("bundle-pool", entityId, result.workerMetadata(), result.applied(), result.fallbackUsed(), result.degradeReason());
        payload.put("featureVector", featureVector);
        payload.put("bundleProposals", result.proposals());
        write(HarvestFamily.GREEDRL_TEACHER_TRACE, traceId, new HarvestEventEnvelope(
                "greedrl-teacher-trace/v1",
                "candidate",
                traceId,
                traceId,
                null,
                "bundle-pool",
                "teacher",
                entityId,
                entityId,
                null,
                Instant.now(),
                null,
                payload));
    }

    public void recordForecastTeacher(String traceId,
                                      String entityId,
                                      String forecastKind,
                                      Object featureVector,
                                      ForecastResult result) {
        if (result == null) {
            return;
        }
        LinkedHashMap<String, Object> payload = teacherPayload("scenario-evaluation", entityId, result.workerMetadata(), result.applied(), result.fallbackUsed(), result.degradeReason());
        payload.put("forecastKind", forecastKind);
        payload.put("featureVector", featureVector);
        payload.put("probability", result.probability());
        payload.put("confidence", result.confidence());
        payload.put("horizonMinutes", result.horizonMinutes());
        payload.put("quantiles", result.quantiles());
        write(HarvestFamily.FORECAST_TEACHER_TRACE, traceId, new HarvestEventEnvelope(
                "forecast-teacher-trace/v1",
                "candidate",
                traceId,
                traceId,
                null,
                "scenario-evaluation",
                "teacher",
                entityId,
                entityId,
                null,
                Instant.now(),
                null,
                payload));
    }

    public void recordDispatchExecution(DispatchV2Request request,
                                        DispatchExecutorStage executorStage,
                                        DecisionStageOutputV1 executionOutput,
                                        List<String> selectedProposalIds) {
        if (request == null || executorStage == null) {
            return;
        }
        DispatchExecutionSummary summary = executorStage.dispatchExecutionSummary();
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("selectedProposalIds", selectedProposalIds == null ? List.of() : selectedProposalIds);
        payload.put("executionBrainSelectedIds", executionOutput == null ? List.of() : executionOutput.selectedIds());
        payload.put("assignmentIds", executorStage.assignments().stream().map(DispatchAssignment::assignmentId).toList());
        payload.put("selectedProposalCount", summary.selectedProposalCount());
        payload.put("executedAssignmentCount", summary.executedAssignmentCount());
        payload.put("conflictFreeValidation", summary.resolvedButRejectedCount() == 0);
        payload.put("fallbackReason", executionOutput != null && executionOutput.meta().fallbackUsed() ? executionOutput.meta().fallbackReason() : "");
        payload.put("degradeReasons", summary.degradeReasons());
        write(HarvestFamily.DISPATCH_EXECUTION, request.traceId(), new HarvestEventEnvelope(
                "dispatch-execution-bronze/v1",
                "stage",
                request.traceId(),
                request.traceId(),
                tickId(request),
                "dispatch-executor",
                "execution",
                request.traceId(),
                null,
                null,
                request.decisionTime(),
                null,
                payload));
    }

    public void recordDispatchOutcome(DispatchV2Request request,
                                      DispatchExecutorStage executorStage,
                                      List<String> degradeReasons) {
        if (request == null || executorStage == null) {
            return;
        }
        double avgPickupEtaSeconds = executorStage.assignments().stream()
                .mapToDouble(assignment -> assignment.projectedPickupEtaMinutes() * 60.0)
                .average()
                .orElse(0.0);
        double avgCompletionSeconds = executorStage.assignments().stream()
                .mapToDouble(assignment -> assignment.projectedCompletionEtaMinutes() * 60.0)
                .average()
                .orElse(0.0);
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("assignmentIds", executorStage.assignments().stream().map(DispatchAssignment::assignmentId).toList());
        payload.put("actualPickupTravelTimeSeconds", avgPickupEtaSeconds);
        payload.put("actualMerchantWaitTimeSeconds", 0.0);
        payload.put("actualDropoffTravelTimeSeconds", Math.max(0.0, avgCompletionSeconds - avgPickupEtaSeconds));
        payload.put("totalCompletionTimeSeconds", avgCompletionSeconds);
        payload.put("realizedTrafficDelaySeconds", 0.0);
        payload.put("realizedWeatherModifier", 1.0);
        payload.put("delivered", !executorStage.assignments().isEmpty());
        payload.put("labelQuality", "SIMULATED_STRONG");
        payload.put("degradeReasons", degradeReasons == null ? List.of() : degradeReasons);
        write(HarvestFamily.DISPATCH_OUTCOME, request.traceId(), new HarvestEventEnvelope(
                "dispatch-outcome-bronze/v1",
                "stage",
                request.traceId(),
                request.traceId(),
                tickId(request),
                "dispatch-outcome",
                "outcome",
                request.traceId(),
                null,
                null,
                null,
                Instant.now(),
                payload));
    }

    private void writeGeospatialSideFamilies(DecisionStageInputV1 input,
                                             String entityId,
                                             String candidateId,
                                             Map<String, Object> row) {
        write(HarvestFamily.BUNDLE_GEOMETRY_TRACE, input.runId(), candidateEnvelope(input, entityId, candidateId, Map.of(
                "bundleCentroidLat", row.getOrDefault("bundleCentroidLat", 0.0),
                "bundleCentroidLng", row.getOrDefault("bundleCentroidLng", 0.0),
                "pickupClusterRadiusMeters", row.getOrDefault("pickupClusterRadiusMeters", 0.0),
                "dropClusterRadiusMeters", row.getOrDefault("dropClusterRadiusMeters", 0.0),
                "routeSpreadMeters", row.getOrDefault("routeSpreadMeters", 0.0),
                "bundleCompactnessScore", row.getOrDefault("bundleCompactnessScore", 0.0),
                "boundaryParticipation", row.getOrDefault("boundaryParticipation", 0.0),
                "avgPairSupport", row.getOrDefault("avgPairSupport", 0.0))));
        if (row.containsKey("driverLat")) {
            write(HarvestFamily.DRIVER_PICKUP_FIT_TRACE, input.runId(), candidateEnvelope(input, entityId, candidateId, Map.of(
                    "driverLat", row.getOrDefault("driverLat", 0.0),
                    "driverLng", row.getOrDefault("driverLng", 0.0),
                    "firstPickupLat", row.getOrDefault("pickupLat", 0.0),
                    "firstPickupLng", row.getOrDefault("pickupLng", 0.0),
                    "driverToFirstPickupDistanceMeters", row.getOrDefault("driverToFirstPickupDistanceMeters", row.getOrDefault("effectiveDistanceMeters", 0.0)),
                    "driverToFirstPickupEtaSeconds", row.getOrDefault("driverToFirstPickupEtaSeconds", 0.0),
                    "deadheadDistanceMeters", row.getOrDefault("deadheadDistanceMeters", 0.0),
                    "driverFitScore", row.getOrDefault("driverFitScore", row.getOrDefault("score", 0.0)))));
        }
        Map<String, Object> geospatialContext = input.geospatialContext();
        Object selectedTiles = geospatialContext.get("selectedTiles");
        if (selectedTiles instanceof List<?> tiles) {
            int ordinal = 0;
            for (Object tile : tiles) {
                if (!(tile instanceof Map<?, ?> map)) {
                    continue;
                }
                ordinal++;
                LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
                payload.put("tileOrdinal", ordinal);
                payload.putAll(castMap(map));
                write(HarvestFamily.GEO_TILE_SELECTION_TRACE, input.runId(), candidateEnvelope(input, entityId, candidateId + ":tile:" + ordinal, payload));
            }
        }
        Object tileSummaries = geospatialContext.get("tileContextSummaries");
        if (tileSummaries instanceof List<?> summaries) {
            int ordinal = 0;
            for (Object summary : summaries) {
                if (!(summary instanceof Map<?, ?> map)) {
                    continue;
                }
                ordinal++;
                write(HarvestFamily.TILE_FEATURE_TRACE, input.runId(), candidateEnvelope(input, entityId, candidateId + ":feature:" + ordinal, castMap(map)));
            }
        }
        Map<String, Object> corridorSummary = castMap(geospatialContext.get("corridorSummary"));
        if (!corridorSummary.isEmpty()) {
            LinkedHashMap<String, Object> payload = new LinkedHashMap<>(corridorSummary);
            payload.put("zoneId", input.dispatchContext().getOrDefault("zoneId", "zone-unknown"));
            payload.put("timeBucket", input.dispatchContext().getOrDefault("hourBucket", "unknown"));
            payload.put("avgSpeedMps", corridorSummary.getOrDefault("avgExpectedSpeedMps", 0.0));
            payload.put("jamClass", input.dispatchContext().getOrDefault("trafficClass", "unknown"));
            payload.put("sourceProvenance", Map.of(
                    "trafficSource", input.dispatchContext().getOrDefault("trafficClass", "unknown"),
                    "weatherSource", input.dispatchContext().getOrDefault("weatherClass", "unknown"),
                    "kind", "estimated"));
            write(HarvestFamily.TRAFFIC_CONTEXT_TRACE, input.runId(), candidateEnvelope(input, entityId, candidateId, payload));
        }
    }

    private HarvestEventEnvelope candidateEnvelope(DecisionStageInputV1 input,
                                                   String entityId,
                                                   String candidateId,
                                                   Map<String, Object> payload) {
        return new HarvestEventEnvelope(
                "bronze-candidate-row/v1",
                "candidate",
                input.traceId(),
                input.runId(),
                input.tickId(),
                input.stageName().wireName(),
                entityType(input.stageName()),
                entityId,
                candidateId,
                null,
                instant(input.dispatchContext().get("decisionTime")),
                null,
                payload);
    }

    private LinkedHashMap<String, Object> teacherPayload(String stageName,
                                                         String entityId,
                                                         MlWorkerMetadata metadata,
                                                         boolean applied,
                                                         boolean fallbackUsed,
                                                         String notAppliedReason) {
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("traceId", entityId);
        payload.put("stageName", stageName);
        payload.put("entityId", entityId);
        payload.put("modelVersion", metadata == null ? "" : metadata.modelVersion());
        payload.put("artifactDigest", metadata == null ? "" : metadata.artifactDigest());
        payload.put("fingerprint", metadata == null ? "" : metadata.sourceModel() + "|" + metadata.modelVersion());
        payload.put("fallbackUsed", fallbackUsed);
        payload.put("applied", applied);
        payload.put("notAppliedReason", notAppliedReason == null ? "" : notAppliedReason);
        return payload;
    }

    private List<Map<String, Object>> candidateRows(Map<String, Object> candidateSet) {
        Object raw = candidateSet.get("window");
        if (!(raw instanceof List<?> rows)) {
            return List.of();
        }
        List<Map<String, Object>> normalized = new ArrayList<>();
        for (Object row : rows) {
            if (row instanceof Map<?, ?> map) {
                normalized.add(castMap(map));
            }
        }
        return List.copyOf(normalized);
    }

    private Map<String, Map<String, Object>> assessmentItems(Map<String, Object> assessments) {
        Object rawItems = assessments.get("items");
        if (!(rawItems instanceof List<?> items)) {
            return Map.of();
        }
        LinkedHashMap<String, Map<String, Object>> mapped = new LinkedHashMap<>();
        for (Object item : items) {
            if (!(item instanceof Map<?, ?> map)) {
                continue;
            }
            Map<String, Object> cast = castMap(map);
            String id = String.valueOf(cast.getOrDefault("id", ""));
            if (!id.isBlank()) {
                mapped.put(id, cast);
            }
        }
        return Map.copyOf(mapped);
    }

    private String candidateId(DecisionStageName stageName, Map<String, Object> row) {
        String bundleId = String.valueOf(row.getOrDefault("bundleId", ""));
        String anchorOrderId = String.valueOf(row.getOrDefault("anchorOrderId", ""));
        String driverId = String.valueOf(row.getOrDefault("driverId", ""));
        String proposalId = String.valueOf(row.getOrDefault("proposalId", row.getOrDefault("id", "")));
        return switch (stageName) {
            case PAIR_BUNDLE -> "bundle:" + String.valueOf(row.getOrDefault("bundleId", row.getOrDefault("id", "")));
            case ANCHOR -> "anchor:%s:%s".formatted(bundleId, anchorOrderId);
            case DRIVER -> "driver:%s:%s".formatted(bundleId, driverId);
            case ROUTE_GENERATION, ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> "proposal:" + proposalId;
            case SAFETY_EXECUTE -> "assignment:" + String.valueOf(row.getOrDefault("id", proposalId));
            case OBSERVATION_PACK -> "observation:" + proposalId;
        };
    }

    private String entityType(DecisionStageName stageName) {
        return switch (stageName) {
            case PAIR_BUNDLE -> "bundle";
            case ANCHOR -> "anchor";
            case DRIVER -> "driver";
            case ROUTE_GENERATION, ROUTE_CRITIQUE, SCENARIO, FINAL_SELECTION -> "proposal";
            case SAFETY_EXECUTE -> "assignment";
            case OBSERVATION_PACK -> "observation";
        };
    }

    private Instant instant(Object value) {
        return value instanceof Instant instant ? instant : null;
    }

    private String tickId(DispatchV2Request request) {
        return request.decisionTime() == null ? "tick-unknown" : request.decisionTime().toString();
    }

    private LinkedHashMap<String, Object> castMap(Object value) {
        if (!(value instanceof Map<?, ?> map)) {
            return new LinkedHashMap<>();
        }
        LinkedHashMap<String, Object> cast = new LinkedHashMap<>();
        map.forEach((key, item) -> cast.put(String.valueOf(key), item));
        return cast;
    }

    private void write(HarvestFamily family, String runId, HarvestEventEnvelope envelope) {
        writer.write(family, runId, envelope.toMap());
    }
}
