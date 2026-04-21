package com.routechain.v2.decision;

public final class StudentBrain implements DecisionBrain {
    private final LegacyMlBrain legacyMlBrain;

    public StudentBrain(LegacyMlBrain legacyMlBrain) {
        this.legacyMlBrain = legacyMlBrain;
    }

    @Override
    public DecisionStageOutputV1 evaluateStage(DecisionStageInputV1 input) {
        DecisionStageOutputV1 legacy = legacyMlBrain.evaluateStage(input);
        return new DecisionStageOutputV1(
                legacy.schemaVersion(),
                legacy.traceId(),
                legacy.runId(),
                legacy.tickId(),
                legacy.stageName(),
                DecisionBrainType.STUDENT,
                "student-placeholder",
                legacy.assessments(),
                legacy.selectedIds(),
                new DecisionStageMetaV1(
                        "decision-stage-meta/v1",
                        legacy.meta().latencyMs(),
                        legacy.meta().confidence(),
                        true,
                        "student-brain-not-trained",
                        true,
                        "legacy",
                        null,
                        null,
                        java.util.Map.of(),
                        0,
                        null,
                        "student",
                        legacy.meta().authoritativeStageSet(),
                        java.util.List.of("student-not-trained"),
                        legacy.meta().contextProfile(),
                        legacy.meta().overlaySet(),
                        legacy.meta().contextCompressionApplied(),
                        "student-fallback"));
    }
}
