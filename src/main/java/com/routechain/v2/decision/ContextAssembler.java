package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.EtaContext;
import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.bundle.DispatchBundleStage;
import com.routechain.v2.cluster.DispatchPairClusterStage;
import com.routechain.v2.executor.DispatchExecutorStage;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DispatchRouteProposalStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.PickupAnchor;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.scenario.DispatchScenarioStage;
import com.routechain.v2.scenario.RobustUtility;
import com.routechain.v2.selector.DispatchSelectorStage;
import com.routechain.v2.selector.SelectorCandidate;

import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class ContextAssembler {
    private final RouteChainDispatchV2Properties properties;
    private final ContextToolRegistry contextToolRegistry;
    private final ContextSelector contextSelector;
    private final ReferenceFrameBuilder referenceFrameBuilder;
    private final ComparisonPackBuilder comparisonPackBuilder;
    private final GeospatialContextAssembler geospatialContextAssembler;
    private final BurstContextAssembler burstContextAssembler;

    public ContextAssembler(RouteChainDispatchV2Properties properties, ContextToolRegistry contextToolRegistry) {
        this.properties = properties;
        this.contextToolRegistry = contextToolRegistry;
        this.contextSelector = new ContextSelector(properties.getDecision());
        this.referenceFrameBuilder = new ReferenceFrameBuilder();
        this.comparisonPackBuilder = new ComparisonPackBuilder();
        this.geospatialContextAssembler = new GeospatialContextAssembler();
        this.burstContextAssembler = new BurstContextAssembler();
    }

    public DecisionStageInputV1 observationInput(DispatchV2Request request) {
        Map<String, Object> dispatchContext = dispatchContext(request, null);
        Map<String, Object> candidateSet = Map.of("topIds", List.of(), "window", List.of());
        return stageInput(
                request,
                DecisionStageName.OBSERVATION_PACK,
                dispatchContext,
                candidateSet,
                List.of(),
                Map.of("summary", "normalized world state only"));
    }

    public DecisionStageInputV1 pairBundleInput(DispatchV2Request request,
                                                EtaContext etaContext,
                                                DispatchPairClusterStage pairClusterStage,
                                                DispatchBundleStage bundleStage) {
        Map<String, Order> ordersById = ordersById(request);
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", bundleStage.bundleCandidates().stream().limit(12).map(BundleCandidate::bundleId).toList(),
                "window", bundleStage.bundleCandidates().stream().limit(12).map(bundle -> bundleWindowRow(bundle, ordersById)).toList(),
                "bundleCount", bundleStage.bundleCandidates().size(),
                "microClusterCount", pairClusterStage.microClusters().size(),
                "pairEdgeCount", pairClusterStage.pairSimilarityGraph().edges().size());
        return stageInput(
                request,
                DecisionStageName.PAIR_BUNDLE,
                dispatchContext,
                candidateSet,
                List.of("observation-pack"),
                Map.of(
                        "previousStage", "observation-pack",
                        "openOrderCount", request.openOrders().size(),
                        "microClusterCount", pairClusterStage.microClusters().size()));
    }

    public DecisionStageInputV1 anchorInput(DispatchV2Request request,
                                            EtaContext etaContext,
                                            DispatchRouteCandidateStage routeCandidateStage) {
        Map<String, Order> ordersById = ordersById(request);
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", routeCandidateStage.pickupAnchors().stream().limit(6).map(PickupAnchor::anchorOrderId).toList(),
                "window", routeCandidateStage.pickupAnchors().stream().limit(6).map(anchor -> anchorWindowRow(anchor, ordersById)).toList(),
                "anchorCount", routeCandidateStage.pickupAnchors().size());
        return stageInput(
                request,
                DecisionStageName.ANCHOR,
                dispatchContext,
                candidateSet,
                List.of("pair-bundle"),
                Map.of(
                        "previousStage", "pair-bundle",
                        "bundleCount", routeCandidateStage.pickupAnchors().stream().map(PickupAnchor::bundleId).distinct().count()));
    }

    public DecisionStageInputV1 driverInput(DispatchV2Request request,
                                            EtaContext etaContext,
                                            DispatchRouteCandidateStage routeCandidateStage) {
        Map<String, Order> ordersById = ordersById(request);
        Map<String, Driver> driversById = driversById(request);
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", routeCandidateStage.driverCandidates().stream().limit(8).map(DriverCandidate::driverId).toList(),
                "window", routeCandidateStage.driverCandidates().stream().limit(8).map(candidate -> driverWindowRow(candidate, driversById, ordersById)).toList(),
                "driverCandidateCount", routeCandidateStage.driverCandidates().size());
        return stageInput(
                request,
                DecisionStageName.DRIVER,
                dispatchContext,
                candidateSet,
                List.of("anchor"),
                Map.of(
                        "previousStage", "anchor",
                        "anchorCount", routeCandidateStage.pickupAnchors().size(),
                        "driverCandidateCount", routeCandidateStage.driverCandidates().size()));
    }

    public DecisionStageInputV1 routeGenerationInput(DispatchV2Request request,
                                                     EtaContext etaContext,
                                                     DispatchRouteProposalStage routeProposalStage) {
        Map<String, Order> ordersById = ordersById(request);
        Map<String, Driver> driversById = driversById(request);
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", routeProposalStage.routeProposals().stream().limit(4).map(RouteProposal::proposalId).toList(),
                "window", routeProposalStage.routeProposals().stream().limit(4).map(proposal -> routeWindowRow(proposal, ordersById, driversById)).toList(),
                "proposalCount", routeProposalStage.routeProposals().size());
        return stageInput(
                request,
                DecisionStageName.ROUTE_GENERATION,
                dispatchContext,
                candidateSet,
                List.of("driver"),
                Map.of(
                        "previousStage", "driver",
                        "driverCandidateCount", routeProposalStage.routeProposals().stream().map(RouteProposal::driverId).distinct().count(),
                        "proposalCount", routeProposalStage.routeProposals().size()));
    }

    public DecisionStageInputV1 routeCritiqueInput(DispatchV2Request request,
                                                   EtaContext etaContext,
                                                   DispatchRouteProposalStage routeProposalStage) {
        Map<String, Order> ordersById = ordersById(request);
        Map<String, Driver> driversById = driversById(request);
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", routeProposalStage.routeProposals().stream().limit(4).map(RouteProposal::proposalId).toList(),
                "window", routeProposalStage.routeProposals().stream().limit(4).map(proposal -> routeWindowRow(proposal, ordersById, driversById)).toList(),
                "proposalCount", routeProposalStage.routeProposals().size(),
                "geometryAvailableCount", routeProposalStage.routeProposals().stream().filter(RouteProposal::geometryAvailable).count());
        return stageInput(
                request,
                DecisionStageName.ROUTE_CRITIQUE,
                dispatchContext,
                candidateSet,
                List.of("route-generation"),
                Map.of(
                        "previousStage", "route-generation",
                        "geometryAvailableCount", routeProposalStage.routeProposals().stream().filter(RouteProposal::geometryAvailable).count(),
                        "proposalCount", routeProposalStage.routeProposals().size()));
    }

    public DecisionStageInputV1 scenarioInput(DispatchV2Request request,
                                              EtaContext etaContext,
                                              DispatchScenarioStage scenarioStage) {
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", scenarioStage.robustUtilities().stream().limit(3).map(RobustUtility::proposalId).toList(),
                "window", scenarioStage.robustUtilities().stream().limit(3).map(this::scenarioWindowRow).toList(),
                "robustUtilityCount", scenarioStage.robustUtilities().size(),
                "scenarioEvaluationCount", scenarioStage.scenarioEvaluations().size());
        DecisionStageInputV1 input = stageInput(
                request,
                DecisionStageName.SCENARIO,
                dispatchContext,
                candidateSet,
                List.of("route-critique"),
                Map.of(
                        "previousStage", "route-critique",
                        "scenarioEvaluationCount", scenarioStage.scenarioEvaluations().size(),
                        "robustUtilityCount", scenarioStage.robustUtilities().size()));
        return input.withBurstContext(mergeMap(input.burstContext(), Map.of(
                "forecastDegradeReasons", scenarioStage.degradeReasons(),
                "freshnessForecastAgeMs", scenarioStage.freshnessMetadata().forecastAgeMs(),
                "forecastFresh", scenarioStage.freshnessMetadata().forecastFresh())));
    }

    public DecisionStageInputV1 finalSelectionInput(DispatchV2Request request,
                                                    EtaContext etaContext,
                                                    DispatchSelectorStage selectorStage) {
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", selectorStage.selectorCandidates().stream().limit(3).map(SelectorCandidate::proposalId).toList(),
                "window", selectorStage.selectorCandidates().stream().limit(3).map(this::selectorWindowRow).toList(),
                "selectorCandidateCount", selectorStage.selectorCandidates().size(),
                "selectedProposalIds", selectorStage.globalSelectionResult().selectedProposals().stream()
                        .map(selectedProposal -> selectedProposal.proposalId())
                        .toList());
        return stageInput(
                request,
                DecisionStageName.FINAL_SELECTION,
                dispatchContext,
                candidateSet,
                List.of("scenario"),
                Map.of(
                        "previousStage", "scenario",
                        "selectorCandidateCount", selectorStage.selectorCandidates().size(),
                        "selectedProposalIds", selectorStage.globalSelectionResult().selectedProposals().stream()
                                .map(selectedProposal -> selectedProposal.proposalId())
                                .toList()));
    }

    public DecisionStageInputV1 safetyExecuteInput(DispatchV2Request request,
                                                   EtaContext etaContext,
                                                   DispatchExecutorStage executorStage) {
        Map<String, Object> dispatchContext = dispatchContext(request, etaContext);
        Map<String, Object> candidateSet = Map.of(
                "topIds", executorStage.assignments().stream().map(assignment -> assignment.assignmentId()).toList(),
                "assignmentCount", executorStage.assignments().size());
        return stageInput(
                request,
                DecisionStageName.SAFETY_EXECUTE,
                dispatchContext,
                candidateSet,
                List.of("final-selection"),
                Map.of(
                        "previousStage", "final-selection",
                        "assignmentCount", executorStage.assignments().size()));
    }

    private DecisionStageInputV1 stageInput(DispatchV2Request request,
                                            DecisionStageName stageName,
                                            Map<String, Object> dispatchContext,
                                            Map<String, Object> candidateSet,
                                            List<String> upstreamRefs,
                                            Map<String, Object> upstreamSummary) {
        ContextSelectionProfile selectionProfile = contextSelector.select(stageName, dispatchContext, candidateSet, upstreamRefs);
        Map<String, Object> enrichedConstraints = new LinkedHashMap<>();
        enrichedConstraints.put("staticPrefix", staticPrefix(stageName));
        enrichedConstraints.put("schemaContract", "stage_output_v1");
        enrichedConstraints.put("contextBudget", stageBudget(stageName));
        enrichedConstraints.put("strictStructuredOutputs", properties.getDecision().getLlm().isStrictStructuredOutputs());
        enrichedConstraints.put("parallelToolCalls", properties.getDecision().getLlm().isParallelToolCalls());
        enrichedConstraints.put("toolManifest", contextToolRegistry.toolManifest(stageName));
        Map<String, Object> referenceFrame = referenceFrameBuilder.build(stageName, candidateSet);
        Map<String, Object> comparisonPack = comparisonPackBuilder.build(candidateSet, referenceFrame);
        Map<String, Object> geospatialContext = geospatialContextAssembler.build(stageName, candidateSet, dispatchContext);
        Map<String, Object> burstContext = burstContextAssembler.build(stageName, dispatchContext, candidateSet);
        return new DecisionStageInputV1(
                "stage-input-v1",
                request.traceId(),
                request.traceId(),
                tickId(request.decisionTime()),
                stageName,
                dispatchContext,
                candidateSet,
                referenceFrame,
                comparisonPack,
                geospatialContext,
                burstContext,
                Map.copyOf(enrichedConstraints),
                Map.of(
                        "profileName", selectionProfile.profileName(),
                        "compressed", selectionProfile.compressed(),
                        "overlays", selectionProfile.overlays(),
                        "toolFetchPlan", selectionProfile.toolFetchPlan(),
                        "qualityFlags", selectionProfile.qualityFlags(),
                        "summary", selectionProfile.summary(),
                        "selectedContext", selectionProfile.selectedContext()),
                upstreamSummary == null ? Map.of() : Map.copyOf(upstreamSummary),
                Map.of(
                        "correctness", 0.35,
                        "latency", 0.15,
                        "robustness", 0.20,
                        "conflict_free", 0.10,
                        "route_value", 0.10,
                        "driver_fit", 0.05,
                        "burst_positioning", 0.05),
                upstreamRefs);
    }

    private Map<String, Object> dispatchContext(DispatchV2Request request, EtaContext etaContext) {
        Map<String, Object> context = new LinkedHashMap<>();
        Instant decisionTime = request.decisionTime();
        int decisionHour = decisionHour(decisionTime);
        context.put("decisionTime", decisionTime);
        context.put("hourBucket", "%02d:00-%02d:59".formatted(decisionHour, decisionHour));
        context.put("dayType", decisionTime == null ? "unknown" : switch (decisionTime.atZone(ZoneOffset.UTC).getDayOfWeek()) {
            case SATURDAY, SUNDAY -> "weekend";
            default -> "weekday";
        });
        context.put("weatherProfile", String.valueOf(request.weatherProfile()));
        context.put("weatherClass", String.valueOf(request.weatherProfile()).toLowerCase().contains("rain") ? "rain" : "clear");
        context.put("trafficClass", etaContext == null ? "unknown" : etaContext.trafficBadSignal() ? "stressed" : "normal");
        context.put("baselineEtaMinutes", etaContext == null ? 0.0 : etaContext.averageEtaMinutes());
        context.put("liveEtaMinutes", etaContext == null ? 0.0 : etaContext.maxEtaMinutes());
        context.put("uncertainty", etaContext == null ? 0.0 : etaContext.averageUncertainty());
        context.put("trafficBad", etaContext != null && etaContext.trafficBadSignal());
        context.put("weatherBad", etaContext != null && etaContext.weatherBadSignal());
        context.put("corridorSignature", etaContext == null ? "unknown-corridor" : etaContext.corridorId());
        context.put("zoneId", etaContext == null ? "zone-unknown" : etaContext.corridorId());
        context.put("decisionMode", properties.getDecision().getMode());
        context.put("authorityMode", properties.getDecision().getMode());
        context.put("authoritativeStages", properties.getDecision().getAuthoritativeStages());
        context.put("activeProfile", properties.getDecision().getContextSelection().isDynamicEnabled() ? "dynamic" : "static");
        context.put("decisionProfile", properties.getDecision().getMode());
        context.put("systemLoad", request.openOrders().size() + "/" + request.availableDrivers().size());
        context.put("openOrderCount", request.openOrders().size());
        context.put("availableDriverCount", request.availableDrivers().size());
        context.put("regionCount", request.regions().size());
        context.put("supplyDemandRatio", request.availableDrivers().isEmpty()
                ? 0.0
                : request.openOrders().size() / (double) request.availableDrivers().size());
        context.put("lateHour", decisionHour >= 21 || decisionHour <= 5);
        context.put("routeAmbiguityScore", etaContext == null ? 0.0 : etaContext.averageUncertainty());
        context.put("llmLatencyPressureMs", properties.getPerformance().getTotalDispatchBudget().toMillis());
        context.put("fallbackHistory", List.of());
        return Map.copyOf(context);
    }

    private Map<String, Object> bundleWindowRow(BundleCandidate bundle, Map<String, Order> ordersById) {
        LinkedHashMap<String, Object> row = baseRow(bundle.bundleId(), bundle.bundleId(), null, null);
        row.put("family", bundle.family().name());
        row.put("orderCount", bundle.orderIds().size());
        row.put("boundaryCross", bundle.boundaryCross());
        row.put("score", bundle.score());
        row.put("feasible", bundle.feasible());
        centroidFields(row, bundle.orderIds().stream().map(ordersById::get).toList());
        return Map.copyOf(row);
    }

    private Map<String, Object> anchorWindowRow(PickupAnchor anchor, Map<String, Order> ordersById) {
        LinkedHashMap<String, Object> row = baseRow(anchor.anchorOrderId(), anchor.bundleId(), null, anchor.anchorOrderId());
        row.put("anchorRank", anchor.anchorRank());
        row.put("score", anchor.score());
        Order anchorOrder = ordersById.get(anchor.anchorOrderId());
        if (anchorOrder != null) {
            geoFields(row, anchorOrder.pickupPoint().latitude(), anchorOrder.pickupPoint().longitude(), "pickup");
            row.put("dropLat", anchorOrder.dropoffPoint().latitude());
            row.put("dropLng", anchorOrder.dropoffPoint().longitude());
        }
        return Map.copyOf(row);
    }

    private Map<String, Object> driverWindowRow(DriverCandidate driverCandidate,
                                                Map<String, Driver> driversById,
                                                Map<String, Order> ordersById) {
        LinkedHashMap<String, Object> row = baseRow(driverCandidate.driverId(), driverCandidate.bundleId(), driverCandidate.driverId(), driverCandidate.anchorOrderId());
        row.put("pickupEtaMinutes", driverCandidate.pickupEtaMinutes());
        row.put("driverFitScore", driverCandidate.driverFitScore());
        row.put("rerankScore", driverCandidate.rerankScore());
        Driver driver = driversById.get(driverCandidate.driverId());
        Order anchorOrder = ordersById.get(driverCandidate.anchorOrderId());
        if (driver != null) {
            row.put("driverLat", driver.currentLocation().latitude());
            row.put("driverLng", driver.currentLocation().longitude());
        }
        if (anchorOrder != null) {
            row.put("pickupLat", anchorOrder.pickupPoint().latitude());
            row.put("pickupLng", anchorOrder.pickupPoint().longitude());
            row.put("dropLat", anchorOrder.dropoffPoint().latitude());
            row.put("dropLng", anchorOrder.dropoffPoint().longitude());
            row.put("driverToFirstPickupEtaSeconds", driverCandidate.pickupEtaMinutes() * 60.0);
            row.put("effectiveDistanceMeters", haversineMeters(
                    driver == null ? 0.0 : driver.currentLocation().latitude(),
                    driver == null ? 0.0 : driver.currentLocation().longitude(),
                    anchorOrder.pickupPoint().latitude(),
                    anchorOrder.pickupPoint().longitude()));
            row.put("haversineDistanceMeters", row.get("effectiveDistanceMeters"));
        }
        return Map.copyOf(row);
    }

    private Map<String, Object> routeWindowRow(RouteProposal proposal,
                                               Map<String, Order> ordersById,
                                               Map<String, Driver> driversById) {
        LinkedHashMap<String, Object> row = baseRow(proposal.proposalId(), proposal.bundleId(), proposal.driverId(), proposal.anchorOrderId());
        row.put("routeValue", proposal.routeValue());
        row.put("projectedPickupEtaMinutes", proposal.projectedPickupEtaMinutes());
        row.put("projectedCompletionEtaMinutes", proposal.projectedCompletionEtaMinutes());
        row.put("geometryAvailable", proposal.geometryAvailable());
        row.put("routeCost", proposal.routeCost());
        row.put("congestionScore", proposal.congestionScore());
        row.put("majorRoadRatio", proposal.majorRoadRatio());
        row.put("minorRoadRatio", proposal.minorRoadRatio());
        row.put("turnCount", proposal.turnCount());
        row.put("straightnessScore", proposal.straightnessScore());
        row.put("distanceMeters", proposal.totalDistanceMeters());
        row.put("travelTimeSeconds", proposal.totalTravelTimeSeconds());
        Driver driver = driversById.get(proposal.driverId());
        Order firstStop = proposal.stopOrder().stream().map(ordersById::get).filter(java.util.Objects::nonNull).findFirst().orElse(null);
        List<Order> routeOrders = proposal.stopOrder().stream().map(ordersById::get).filter(java.util.Objects::nonNull).toList();
        if (driver != null) {
            row.put("driverLat", driver.currentLocation().latitude());
            row.put("driverLng", driver.currentLocation().longitude());
        }
        if (firstStop != null) {
            row.put("pickupLat", firstStop.pickupPoint().latitude());
            row.put("pickupLng", firstStop.pickupPoint().longitude());
            row.put("dropLat", firstStop.dropoffPoint().latitude());
            row.put("dropLng", firstStop.dropoffPoint().longitude());
            row.put("driverToFirstPickupEtaSeconds", proposal.projectedPickupEtaMinutes() * 60.0);
            row.put("effectiveDistanceMeters", driver == null ? 0.0 : haversineMeters(
                    driver.currentLocation().latitude(),
                    driver.currentLocation().longitude(),
                    firstStop.pickupPoint().latitude(),
                    firstStop.pickupPoint().longitude()));
            row.put("haversineDistanceMeters", row.get("effectiveDistanceMeters"));
        }
        centroidFields(row, routeOrders);
        row.put("corridorOverlapRatio", proposal.geometryAvailable() ? proposal.majorRoadRatio() : 0.0);
        return Map.copyOf(row);
    }

    private Map<String, Object> scenarioWindowRow(RobustUtility robustUtility) {
        return Map.of(
                "id", robustUtility.proposalId(),
                "proposalId", robustUtility.proposalId(),
                "expectedValue", robustUtility.expectedValue(),
                "worstCaseValue", robustUtility.worstCaseValue(),
                "landingValue", robustUtility.landingValue(),
                "stabilityScore", robustUtility.stabilityScore(),
                "robustUtility", robustUtility.robustUtility(),
                "urgentOrderSurgeScore", robustUtility.stabilityScore(),
                "score", robustUtility.robustUtility());
    }

    private Map<String, Object> selectorWindowRow(SelectorCandidate candidate) {
        return Map.of(
                "id", candidate.proposalId(),
                "proposalId", candidate.proposalId(),
                "bundleId", candidate.bundleId(),
                "driverId", candidate.driverId(),
                "selectionScore", candidate.selectionScore(),
                "robustUtility", candidate.robustUtility(),
                "routeValue", candidate.routeValue(),
                "feasible", candidate.feasible(),
                "score", candidate.selectionScore());
    }

    private LinkedHashMap<String, Object> baseRow(String id, String bundleId, String driverId, String anchorOrderId) {
        LinkedHashMap<String, Object> row = new LinkedHashMap<>();
        row.put("id", id);
        if (bundleId != null) {
            row.put("bundleId", bundleId);
        }
        if (driverId != null) {
            row.put("driverId", driverId);
        }
        if (anchorOrderId != null) {
            row.put("anchorOrderId", anchorOrderId);
        }
        return row;
    }

    private void geoFields(Map<String, Object> row, double lat, double lng, String prefix) {
        row.put(prefix + "Lat", lat);
        row.put(prefix + "Lng", lng);
    }

    private void centroidFields(Map<String, Object> row, List<Order> orders) {
        List<Order> safeOrders = orders.stream().filter(java.util.Objects::nonNull).toList();
        if (safeOrders.isEmpty()) {
            return;
        }
        row.put("pickupClusterRadiusMeters", clusterRadiusMeters(safeOrders, true));
        row.put("dropClusterRadiusMeters", clusterRadiusMeters(safeOrders, false));
        row.put("pickupDropDirectionalConsistency", directionalConsistency(safeOrders));
        row.put("bundleCentroidLat", safeOrders.stream().mapToDouble(order -> order.pickupPoint().latitude()).average().orElse(0.0));
        row.put("bundleCentroidLng", safeOrders.stream().mapToDouble(order -> order.pickupPoint().longitude()).average().orElse(0.0));
        Order first = safeOrders.getFirst();
        row.putIfAbsent("pickupLat", first.pickupPoint().latitude());
        row.putIfAbsent("pickupLng", first.pickupPoint().longitude());
        row.putIfAbsent("dropLat", first.dropoffPoint().latitude());
        row.putIfAbsent("dropLng", first.dropoffPoint().longitude());
    }

    private double clusterRadiusMeters(List<Order> orders, boolean pickup) {
        double centroidLat = orders.stream().mapToDouble(order -> pickup ? order.pickupPoint().latitude() : order.dropoffPoint().latitude()).average().orElse(0.0);
        double centroidLng = orders.stream().mapToDouble(order -> pickup ? order.pickupPoint().longitude() : order.dropoffPoint().longitude()).average().orElse(0.0);
        return orders.stream()
                .mapToDouble(order -> haversineMeters(
                        centroidLat,
                        centroidLng,
                        pickup ? order.pickupPoint().latitude() : order.dropoffPoint().latitude(),
                        pickup ? order.pickupPoint().longitude() : order.dropoffPoint().longitude()))
                .average()
                .orElse(0.0);
    }

    private double directionalConsistency(List<Order> orders) {
        return orders.stream()
                .mapToDouble(order -> {
                    double lat = order.dropoffPoint().latitude() - order.pickupPoint().latitude();
                    double lng = order.dropoffPoint().longitude() - order.pickupPoint().longitude();
                    double magnitude = Math.sqrt((lat * lat) + (lng * lng));
                    return magnitude <= 0.0 ? 1.0 : Math.min(1.0, Math.abs(lat) / magnitude);
                })
                .average()
                .orElse(1.0);
    }

    private String staticPrefix(DecisionStageName stageName) {
        return switch (stageName) {
            case OBSERVATION_PACK -> "Normalize world state. Do not invent entities.";
            case PAIR_BUNDLE -> "Rank pair and bundle candidates under hard dispatch constraints with a reference frame and baseline comparison.";
            case ANCHOR -> "Choose stable pickup anchors with minimal wait, low constraint risk, and clear spatial framing.";
            case DRIVER -> "Prefer driver fit, entry quality, ETA discipline, and operational stability.";
            case ROUTE_GENERATION -> "Generate compact route choices using route vectors, geospatial context, and explicit relative trade-offs.";
            case ROUTE_CRITIQUE -> "Critique route options using route-vector realism, geospatial context, burst positioning, and regret.";
            case SCENARIO -> "Score robustness across weather, traffic, burst demand, and post-drop opportunity.";
            case FINAL_SELECTION -> "Select the safest high-value proposals with conflict-free bias, regret awareness, and burst positioning.";
            case SAFETY_EXECUTE -> "Safety and execution are deterministic; only summarize the selected assignments.";
        };
    }

    private Map<String, Object> stageBudget(DecisionStageName stageName) {
        return switch (stageName) {
            case PAIR_BUNDLE -> Map.of("pairs", 12, "bundles", 12, "layers", 8);
            case ANCHOR -> Map.of("bundles", 6, "anchorsPerBundle", 4, "layers", 8);
            case DRIVER -> Map.of("bundles", 4, "driversPerBundle", 8, "layers", 8);
            case ROUTE_GENERATION -> Map.of("bundles", 1, "drivers", 3, "alternatives", 4, "layers", 8);
            case ROUTE_CRITIQUE -> Map.of("routes", 4, "layers", 8);
            case SCENARIO -> Map.of("proposals", 3, "layers", 8);
            case FINAL_SELECTION -> Map.of("proposals", 3, "layers", 8);
            case OBSERVATION_PACK, SAFETY_EXECUTE -> Map.of("rows", 0, "layers", 4);
        };
    }

    private Map<String, Order> ordersById(DispatchV2Request request) {
        return request.openOrders().stream().collect(Collectors.toMap(Order::orderId, Function.identity(), (left, right) -> left));
    }

    private Map<String, Driver> driversById(DispatchV2Request request) {
        return request.availableDrivers().stream().collect(Collectors.toMap(Driver::driverId, Function.identity(), (left, right) -> left));
    }

    private double haversineMeters(double lat1, double lng1, double lat2, double lng2) {
        double earthRadiusMeters = 6_371_000.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return 2 * earthRadiusMeters * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private String tickId(Instant decisionTime) {
        return decisionTime == null ? "tick-unknown" : decisionTime.toString();
    }

    private int decisionHour(Instant decisionTime) {
        if (decisionTime == null) {
            return 0;
        }
        return decisionTime.atZone(ZoneOffset.UTC).getHour();
    }

    private Map<String, Object> mergeMap(Map<String, Object> left, Map<String, Object> right) {
        LinkedHashMap<String, Object> merged = new LinkedHashMap<>(left == null ? Map.of() : left);
        merged.putAll(right);
        return Map.copyOf(merged);
    }
}
