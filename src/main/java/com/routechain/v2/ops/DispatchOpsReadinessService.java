package com.routechain.v2.ops;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.WarmStartState;
import com.routechain.v2.feedback.WarmStartManager;
import com.routechain.v2.integration.ForecastClient;
import com.routechain.v2.integration.GreedRlClient;
import com.routechain.v2.integration.MlWorkerMetadata;
import com.routechain.v2.integration.ModelManifestLoader;
import com.routechain.v2.integration.RouteFinderClient;
import com.routechain.v2.integration.TabularScoringClient;
import com.routechain.v2.integration.WorkerManifest;
import com.routechain.v2.integration.WorkerReadyState;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class DispatchOpsReadinessService {
    private static final String SNAPSHOT_SCHEMA = "dispatch-ops-readiness-snapshot/v1";

    private final RouteChainDispatchV2Properties properties;
    private final WarmStartManager warmStartManager;
    private final TabularScoringClient tabularScoringClient;
    private final RouteFinderClient routeFinderClient;
    private final GreedRlClient greedRlClient;
    private final ForecastClient forecastClient;
    private final Path manifestPath;
    private final ModelManifestLoader modelManifestLoader;

    public DispatchOpsReadinessService(RouteChainDispatchV2Properties properties,
                                       WarmStartManager warmStartManager,
                                       TabularScoringClient tabularScoringClient,
                                       RouteFinderClient routeFinderClient,
                                       GreedRlClient greedRlClient,
                                       ForecastClient forecastClient,
                                       Path manifestPath) {
        this(properties, warmStartManager, tabularScoringClient, routeFinderClient, greedRlClient, forecastClient, manifestPath, new ModelManifestLoader());
    }

    DispatchOpsReadinessService(RouteChainDispatchV2Properties properties,
                                WarmStartManager warmStartManager,
                                TabularScoringClient tabularScoringClient,
                                RouteFinderClient routeFinderClient,
                                GreedRlClient greedRlClient,
                                ForecastClient forecastClient,
                                Path manifestPath,
                                ModelManifestLoader modelManifestLoader) {
        this.properties = properties;
        this.warmStartManager = warmStartManager;
        this.tabularScoringClient = tabularScoringClient;
        this.routeFinderClient = routeFinderClient;
        this.greedRlClient = greedRlClient;
        this.forecastClient = forecastClient;
        this.manifestPath = manifestPath;
        this.modelManifestLoader = modelManifestLoader;
    }

    public DispatchOpsReadinessSnapshot snapshot() {
        WarmStartState warmStartState = warmStartManager.currentState();
        Map<String, WorkerManifest.WorkerManifestEntry> manifestEntries = loadManifestEntries();
        List<DispatchOpsReadinessSnapshot.DispatchOpsWorkerReadiness> workers = List.of(
                worker("ml-tabular-worker", properties.isMlEnabled() && properties.getMl().getTabular().isEnabled(), tabularScoringClient.readyState(), manifestEntries),
                worker("ml-routefinder-worker", properties.isMlEnabled() && properties.getMl().getRoutefinder().isEnabled(), routeFinderClient.readyState(), manifestEntries),
                worker("ml-greedrl-worker", properties.isMlEnabled() && properties.getMl().getGreedrl().isEnabled(), greedRlClient.readyState(), manifestEntries),
                worker("ml-forecast-worker", properties.isMlEnabled() && properties.getMl().getForecast().isEnabled(), forecastClient.readyState(), manifestEntries));
        List<DispatchOpsReadinessSnapshot.DispatchOpsLiveSourceStatus> liveSources = List.of(
                new DispatchOpsReadinessSnapshot.DispatchOpsLiveSourceStatus(
                        "open-meteo",
                        properties.isOpenMeteoEnabled() && properties.getWeather().isEnabled(),
                        DispatchOpsStatusMapper.openMeteoStatus(
                                properties.isOpenMeteoEnabled() && properties.getWeather().isEnabled(),
                                List.of()),
                        false),
                new DispatchOpsReadinessSnapshot.DispatchOpsLiveSourceStatus(
                        "tomtom-traffic",
                        properties.isTomtomEnabled() && properties.getTraffic().isEnabled(),
                        DispatchOpsStatusMapper.tomTomStatus(
                                properties.isTomtomEnabled() && properties.getTraffic().isEnabled(),
                                !properties.getTraffic().getApiKey().isBlank(),
                                List.of()),
                        !properties.getTraffic().getApiKey().isBlank()));
        return new DispatchOpsReadinessSnapshot(
                SNAPSHOT_SCHEMA,
                properties.isEnabled(),
                properties.isMlEnabled(),
                properties.isSidecarRequired(),
                properties.getFeedback().getStorageMode().name(),
                properties.getFeedback().getBaseDir(),
                properties.isWarmStartEnabled(),
                properties.isHotStartEnabled(),
                properties.getWarmHotStart().isLoadLatestSnapshotOnBoot(),
                warmStartState.bootMode().name(),
                warmStartState.snapshotLoaded(),
                warmStartState.snapshotId(),
                warmStartState.loadedTraceId(),
                warmStartState.degradeReasons(),
                workers,
                liveSources);
    }

    public Map<String, Object> snapshotDetails() {
        return snapshot().toMap();
    }

    private DispatchOpsReadinessSnapshot.DispatchOpsWorkerReadiness worker(String workerName,
                                                                           boolean enabled,
                                                                           WorkerReadyState readyState,
                                                                           Map<String, WorkerManifest.WorkerManifestEntry> manifestEntries) {
        WorkerManifest.WorkerManifestEntry manifestEntry = manifestEntries.get(workerName);
        MlWorkerMetadata metadata = readyState == null ? MlWorkerMetadata.empty() : readyState.workerMetadata();
        String sourceModel = firstNonBlank(metadata.sourceModel(), manifestEntry == null ? "" : manifestEntry.modelName());
        String modelVersion = firstNonBlank(metadata.modelVersion(), manifestEntry == null ? "" : manifestEntry.modelVersion());
        String artifactDigest = firstNonBlank(metadata.artifactDigest(), manifestEntry == null ? "" : manifestEntry.artifactDigest());
        String fingerprint = manifestEntry == null ? "" : blankToEmpty(manifestEntry.loadedModelFingerprint());
        String reason;
        boolean ready;
        if (!enabled) {
            ready = false;
            reason = "worker-disabled";
        } else if (readyState == null) {
            ready = false;
            reason = "worker-state-missing";
        } else {
            ready = readyState.ready();
            reason = ready ? "" : blankToEmpty(readyState.reason());
        }
        return new DispatchOpsReadinessSnapshot.DispatchOpsWorkerReadiness(
                workerName,
                enabled,
                ready,
                reason,
                sourceModel,
                modelVersion,
                artifactDigest,
                fingerprint,
                blankToEmpty(metadata.device()),
                blankToEmpty(metadata.dtype()),
                metadata.gpuMemoryAllocatedMb(),
                metadata.batchSize(),
                blankToEmpty(metadata.compileMode()),
                metadata.modelLoaded(),
                metadata.warmupDone());
    }

    private Map<String, WorkerManifest.WorkerManifestEntry> loadManifestEntries() {
        try {
            WorkerManifest manifest = modelManifestLoader.load(manifestPath);
            Map<String, WorkerManifest.WorkerManifestEntry> entries = new LinkedHashMap<>();
            for (WorkerManifest.WorkerManifestEntry entry : manifest.workers()) {
                entries.put(entry.workerName(), entry);
            }
            return entries;
        } catch (RuntimeException exception) {
            return Map.of();
        }
    }

    private String firstNonBlank(String first, String second) {
        return !blankToEmpty(first).isBlank() ? blankToEmpty(first) : blankToEmpty(second);
    }

    private String blankToEmpty(String value) {
        return value == null ? "" : value;
    }
}
