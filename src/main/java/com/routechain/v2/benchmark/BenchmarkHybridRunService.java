package com.routechain.v2.benchmark;

import com.routechain.api.DashboardController;
import org.springframework.stereotype.Service;

@Service
public final class BenchmarkHybridRunService {
    public DashboardController.RunVisualizationDto run(String jobId,
                                                       DashboardController.BenchmarkJobRequest request,
                                                       BenchmarkRunExecutor executor) {
        return executor.run(jobId, request);
    }

    @FunctionalInterface
    public interface BenchmarkRunExecutor {
        DashboardController.RunVisualizationDto run(String jobId, DashboardController.BenchmarkJobRequest request);
    }
}
