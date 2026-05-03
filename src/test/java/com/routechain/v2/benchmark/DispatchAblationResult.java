package com.routechain.v2.benchmark;

import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.bundle.BundlePoolSummary;
import com.routechain.v2.repair.RepairTelemetry;

import java.util.List;
import java.util.Map;

public record DispatchAblationResult(
        String schemaVersion,
        String scenarioPack,
        String scenarioName,
        String workloadSize,
        String executionMode,
        String toggledComponent,
        Map<String, String> controlConfig,
        Map<String, String> variantConfig,
        DispatchQualityMetrics controlMetrics,
        DispatchQualityMetrics variantMetrics,
        BundlePoolSummary controlBundlePoolSummary,
        BundlePoolSummary variantBundlePoolSummary,
        Map<String, Object> controlSelectorSourceSummary,
        Map<String, Object> variantSelectorSourceSummary,
        RepairTelemetry controlActiveRepairTelemetry,
        RepairTelemetry variantActiveRepairTelemetry,
        Map<String, Object> controlRuntimeTelemetry,
        Map<String, Object> variantRuntimeTelemetry,
        List<MlStageMetadata> controlMlStageMetadata,
        List<MlStageMetadata> variantMlStageMetadata,
        List<String> deltaSummary) implements SchemaVersioned {
}
