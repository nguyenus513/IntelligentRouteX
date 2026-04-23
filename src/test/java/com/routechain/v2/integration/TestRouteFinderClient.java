package com.routechain.v2.integration;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;

public final class TestRouteFinderClient implements RouteFinderClient {
    private final WorkerReadyState readyState;
    private final BiFunction<RouteFinderFeatureVector, Long, RouteFinderResult> refineFunction;
    private final BiFunction<RouteFinderFeatureVector, Long, RouteFinderResult> alternativesFunction;
    private final List<RouteFinderFeatureVector> refineInvocations = new ArrayList<>();
    private final List<RouteFinderFeatureVector> alternativesInvocations = new ArrayList<>();

    public TestRouteFinderClient(WorkerReadyState readyState,
                                 BiFunction<RouteFinderFeatureVector, Long, RouteFinderResult> refineFunction,
                                 BiFunction<RouteFinderFeatureVector, Long, RouteFinderResult> alternativesFunction) {
        this.readyState = readyState;
        this.refineFunction = refineFunction;
        this.alternativesFunction = alternativesFunction;
    }

    public static TestRouteFinderClient applied() {
        MlWorkerMetadata metadata = new MlWorkerMetadata("routefinder-local", "v1", "sha256:routefinder", 7L, "cuda:0", "fp16", 6144L, 4, "inductor", true, true);
        return new TestRouteFinderClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> RouteFinderResult.applied(List.of(refinedRoute(feature)), false, metadata),
                (feature, timeout) -> RouteFinderResult.applied(List.of(alternativeRoute(feature)), false, metadata));
    }

    public static TestRouteFinderClient notApplied(String reason) {
        MlWorkerMetadata metadata = new MlWorkerMetadata("routefinder-local", "v1", "sha256:routefinder", 7L, "cuda:0", "fp16", 6144L, 4, "inductor", true, true);
        return new TestRouteFinderClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> RouteFinderResult.notApplied(reason, metadata),
                (feature, timeout) -> RouteFinderResult.notApplied(reason, metadata));
    }

    @Override
    public RouteFinderResult refineRoute(RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
        refineInvocations.add(featureVector);
        return refineFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public RouteFinderResult generateAlternatives(RouteFinderFeatureVector featureVector, long timeoutBudgetMs) {
        alternativesInvocations.add(featureVector);
        return alternativesFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public WorkerReadyState readyState() {
        return readyState;
    }

    public List<RouteFinderFeatureVector> refineInvocations() {
        return List.copyOf(refineInvocations);
    }

    public List<RouteFinderFeatureVector> alternativesInvocations() {
        return List.copyOf(alternativesInvocations);
    }

    private static RouteFinderRoute alternativeRoute(RouteFinderFeatureVector featureVector) {
        List<String> stopOrder = reordered(featureVector);
        return new RouteFinderRoute(
                stopOrder,
                featureVector.projectedPickupEtaMinutes() + 0.5,
                featureVector.projectedCompletionEtaMinutes() + 1.0,
                0.74,
                List.of("routefinder-alternative"));
    }

    private static RouteFinderRoute refinedRoute(RouteFinderFeatureVector featureVector) {
        List<String> stopOrder = reordered(featureVector);
        return new RouteFinderRoute(
                stopOrder,
                Math.max(0.0, featureVector.projectedPickupEtaMinutes() - 0.3),
                Math.max(featureVector.projectedPickupEtaMinutes() - 0.3, featureVector.projectedCompletionEtaMinutes() - 0.8),
                0.79,
                List.of("routefinder-refined"));
    }

    private static List<String> reordered(RouteFinderFeatureVector featureVector) {
        if (featureVector.baselineStopOrder().size() <= 2) {
            return List.copyOf(featureVector.baselineStopOrder());
        }
        List<String> reordered = new ArrayList<>();
        reordered.add(featureVector.anchorOrderId());
        List<String> remainder = new ArrayList<>(featureVector.baselineStopOrder().subList(1, featureVector.baselineStopOrder().size()));
        java.util.Collections.reverse(remainder);
        reordered.addAll(remainder);
        return List.copyOf(reordered);
    }
}
