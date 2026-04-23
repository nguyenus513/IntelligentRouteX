package com.routechain.v2.integration;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;

public final class TestGreedRlClient implements GreedRlClient {
    private final WorkerReadyState readyState;
    private final BiFunction<GreedRlBundleFeatureVector, Long, GreedRlBundleResult> bundleFunction;
    private final BiFunction<GreedRlSequenceFeatureVector, Long, GreedRlSequenceResult> sequenceFunction;
    private final List<GreedRlBundleFeatureVector> bundleInvocations = new ArrayList<>();
    private final List<GreedRlSequenceFeatureVector> sequenceInvocations = new ArrayList<>();

    public TestGreedRlClient(WorkerReadyState readyState,
                             BiFunction<GreedRlBundleFeatureVector, Long, GreedRlBundleResult> bundleFunction,
                             BiFunction<GreedRlSequenceFeatureVector, Long, GreedRlSequenceResult> sequenceFunction) {
        this.readyState = readyState;
        this.bundleFunction = bundleFunction;
        this.sequenceFunction = sequenceFunction;
    }

    public static TestGreedRlClient applied() {
        MlWorkerMetadata metadata = new MlWorkerMetadata("greedrl-local", "v1", "sha256:greedrl", 9L, "cuda:0", "fp16", 5120L, 6, "inductor", true, true);
        return new TestGreedRlClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> GreedRlBundleResult.applied(List.of(
                        new GreedRlBundleCandidate(
                                "COMPACT_CLIQUE",
                                bundleOrders(feature),
                                feature.acceptedBoundaryOrderIds().stream()
                                        .filter(bundleOrders(feature)::contains)
                                        .toList(),
                                feature.acceptedBoundaryOrderIds().stream().anyMatch(bundleOrders(feature)::contains),
                                List.of("greedrl-bundle-proposal"))), metadata),
                (feature, timeout) -> GreedRlSequenceResult.applied(List.of(
                        new GreedRlSequenceProposal(feature.orderIds(), 0.73, List.of("greedrl-sequence-proposal"))), metadata));
    }

    public static TestGreedRlClient notApplied(String reason) {
        MlWorkerMetadata metadata = new MlWorkerMetadata("greedrl-local", "v1", "sha256:greedrl", 9L, "cuda:0", "fp16", 5120L, 6, "inductor", true, true);
        return new TestGreedRlClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> GreedRlBundleResult.notApplied(reason, metadata),
                (feature, timeout) -> GreedRlSequenceResult.notApplied(reason, metadata));
    }

    @Override
    public GreedRlBundleResult proposeBundles(GreedRlBundleFeatureVector featureVector, long timeoutBudgetMs) {
        bundleInvocations.add(featureVector);
        return bundleFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public GreedRlSequenceResult proposeSequence(GreedRlSequenceFeatureVector featureVector, long timeoutBudgetMs) {
        sequenceInvocations.add(featureVector);
        return sequenceFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public WorkerReadyState readyState() {
        return readyState;
    }

    public List<GreedRlBundleFeatureVector> bundleInvocations() {
        return List.copyOf(bundleInvocations);
    }

    public List<GreedRlSequenceFeatureVector> sequenceInvocations() {
        return List.copyOf(sequenceInvocations);
    }

    private static List<String> bundleOrders(GreedRlBundleFeatureVector feature) {
        List<String> prioritized = feature.prioritizedOrderIds();
        if (prioritized.size() >= 3) {
            return List.of(prioritized.get(1), prioritized.get(2));
        }
        if (prioritized.size() >= 2) {
            return List.of(prioritized.get(0), prioritized.get(1));
        }
        return List.copyOf(prioritized);
    }
}
