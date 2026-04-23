package com.routechain.v2.integration;

import com.routechain.v2.context.EtaFeatureVector;
import com.routechain.v2.cluster.PairFeatureVector;
import com.routechain.v2.route.DriverFitFeatureVector;
import com.routechain.v2.route.RouteValueFeatureVector;

import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;

public final class TestTabularScoringClient implements TabularScoringClient {
    private final WorkerReadyState readyState;
    private final BiFunction<Object, Long, TabularScoreResult> etaScorer;
    private final BiFunction<Object, Long, TabularScoreResult> pairScorer;
    private final BiFunction<Object, Long, TabularScoreResult> driverFitScorer;
    private final BiFunction<Object, Long, TabularScoreResult> routeValueScorer;
    private final List<Object> invocations = new ArrayList<>();

    public TestTabularScoringClient(WorkerReadyState readyState,
                                    BiFunction<Object, Long, TabularScoreResult> etaScorer,
                                    BiFunction<Object, Long, TabularScoreResult> pairScorer,
                                    BiFunction<Object, Long, TabularScoreResult> driverFitScorer,
                                    BiFunction<Object, Long, TabularScoreResult> routeValueScorer) {
        this.readyState = readyState;
        this.etaScorer = etaScorer;
        this.pairScorer = pairScorer;
        this.driverFitScorer = driverFitScorer;
        this.routeValueScorer = routeValueScorer;
    }

    public static TestTabularScoringClient applied(double delta) {
        MlWorkerMetadata metadata = new MlWorkerMetadata("tabular-test", "v1", "sha256:test", 5L, "cpu", "fp32", 0L, 16, "eager", true, true);
        TabularScoreResult result = TabularScoreResult.applied(delta, 0.1, false, metadata);
        return new TestTabularScoringClient(
                WorkerReadyState.ready(metadata),
                (ignored, timeout) -> result,
                (ignored, timeout) -> result,
                (ignored, timeout) -> result,
                (ignored, timeout) -> result);
    }

    public static TestTabularScoringClient notApplied(String reason) {
        MlWorkerMetadata metadata = new MlWorkerMetadata("tabular-test", "v1", "sha256:test", 5L, "cpu", "fp32", 0L, 16, "eager", true, true);
        TabularScoreResult result = TabularScoreResult.notApplied(reason, metadata);
        return new TestTabularScoringClient(
                WorkerReadyState.ready(metadata),
                (ignored, timeout) -> result,
                (ignored, timeout) -> result,
                (ignored, timeout) -> result,
                (ignored, timeout) -> result);
    }

    @Override
    public TabularScoreResult scoreEtaResidual(EtaFeatureVector etaFeatureVector, long timeoutBudgetMs) {
        invocations.add(etaFeatureVector);
        return etaScorer.apply(etaFeatureVector, timeoutBudgetMs);
    }

    @Override
    public TabularScoreResult scorePair(PairFeatureVector pairFeatureVector, long timeoutBudgetMs) {
        invocations.add(pairFeatureVector);
        return pairScorer.apply(pairFeatureVector, timeoutBudgetMs);
    }

    @Override
    public TabularScoreResult scoreDriverFit(DriverFitFeatureVector driverFitFeatureVector, long timeoutBudgetMs) {
        invocations.add(driverFitFeatureVector);
        return driverFitScorer.apply(driverFitFeatureVector, timeoutBudgetMs);
    }

    @Override
    public TabularScoreResult scoreRouteValue(RouteValueFeatureVector routeValueFeatureVector, long timeoutBudgetMs) {
        invocations.add(routeValueFeatureVector);
        return routeValueScorer.apply(routeValueFeatureVector, timeoutBudgetMs);
    }

    @Override
    public WorkerReadyState readyState() {
        return readyState;
    }

    public List<Object> invocations() {
        return List.copyOf(invocations);
    }
}
