package com.routechain.v2.selector;

import com.routechain.v2.SchemaVersioned;
import com.routechain.v2.DispatchStageLatency;
import com.routechain.v2.repair.RepairTelemetry;

import java.util.List;

public record DispatchSelectorStage(
        String schemaVersion,
        List<SelectorCandidate> selectorCandidates,
        ConflictGraph conflictGraph,
        GlobalSelectionResult globalSelectionResult,
        GlobalSelectorSummary globalSelectorSummary,
        List<SelectorObjectiveBreakdown> objectiveBreakdowns,
        RepairTelemetry activeRepairTelemetry,
        List<SelectorTrainingTrace> trainingTraces,
        List<DispatchStageLatency> stageLatencies,
        List<String> degradeReasons) implements SchemaVersioned {

    public DispatchSelectorStage(String schemaVersion,
                                 List<SelectorCandidate> selectorCandidates,
                                 ConflictGraph conflictGraph,
                                 GlobalSelectionResult globalSelectionResult,
                                 GlobalSelectorSummary globalSelectorSummary,
                                 List<SelectorTrainingTrace> trainingTraces,
                                 List<DispatchStageLatency> stageLatencies,
                                 List<String> degradeReasons) {
        this(
                schemaVersion,
                selectorCandidates,
                conflictGraph,
                globalSelectionResult,
                globalSelectorSummary,
                List.of(),
                RepairTelemetry.empty(),
                trainingTraces,
                stageLatencies,
                degradeReasons);
    }
}
