package com.routechain.v2.integration;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;

public final class TestForecastClient implements ForecastClient {
    private final WorkerReadyState readyState;
    private final BiFunction<DemandShiftFeatureVector, Long, ForecastResult> demandShiftFunction;
    private final BiFunction<ZoneBurstFeatureVector, Long, ForecastResult> zoneBurstFunction;
    private final BiFunction<PostDropShiftFeatureVector, Long, ForecastResult> postDropShiftFunction;
    private final List<Object> invocations = new ArrayList<>();

    public TestForecastClient(WorkerReadyState readyState,
                              BiFunction<DemandShiftFeatureVector, Long, ForecastResult> demandShiftFunction,
                              BiFunction<ZoneBurstFeatureVector, Long, ForecastResult> zoneBurstFunction,
                              BiFunction<PostDropShiftFeatureVector, Long, ForecastResult> postDropShiftFunction) {
        this.readyState = readyState;
        this.demandShiftFunction = demandShiftFunction;
        this.zoneBurstFunction = zoneBurstFunction;
        this.postDropShiftFunction = postDropShiftFunction;
    }

    public static TestForecastClient applied() {
        MlWorkerMetadata metadata = new MlWorkerMetadata("chronos-2", "v1", "sha256:chronos", 11L, "cuda:0", "fp16", 4096L, 8, "inductor", true, true);
        return new TestForecastClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> ForecastResult.applied(30, 0.71, Map.of("q10", -0.18, "q50", -0.09, "q90", 0.02), 0.84, 90000L, metadata),
                (feature, timeout) -> ForecastResult.applied(20, 0.74, Map.of("q10", 0.08, "q50", 0.16, "q90", 0.24), 0.82, 80000L, metadata),
                (feature, timeout) -> ForecastResult.applied(45, 0.69, Map.of("q10", 0.04, "q50", 0.12, "q90", 0.20), 0.80, 85000L, metadata));
    }

    public static TestForecastClient notApplied(String reason) {
        MlWorkerMetadata metadata = new MlWorkerMetadata("chronos-2", "v1", "sha256:chronos", 11L, "cuda:0", "fp16", 4096L, 8, "inductor", true, true);
        return new TestForecastClient(
                WorkerReadyState.ready(metadata),
                (feature, timeout) -> ForecastResult.notApplied(reason, metadata),
                (feature, timeout) -> ForecastResult.notApplied(reason, metadata),
                (feature, timeout) -> ForecastResult.notApplied(reason, metadata));
    }

    @Override
    public ForecastResult forecastDemandShift(DemandShiftFeatureVector featureVector, long timeoutBudgetMs) {
        invocations.add(featureVector);
        return demandShiftFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public ForecastResult forecastZoneBurst(ZoneBurstFeatureVector featureVector, long timeoutBudgetMs) {
        invocations.add(featureVector);
        return zoneBurstFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public ForecastResult forecastPostDropShift(PostDropShiftFeatureVector featureVector, long timeoutBudgetMs) {
        invocations.add(featureVector);
        return postDropShiftFunction.apply(featureVector, timeoutBudgetMs);
    }

    @Override
    public WorkerReadyState readyState() {
        return readyState;
    }

    public List<Object> invocations() {
        return List.copyOf(invocations);
    }
}
