package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

record StagePromptSpec(
        DecisionStageName stageName,
        String promptSpecVersion,
        String packetTemplateVersion,
        String skillSetVersion,
        String stagePromptName,
        String systemPromptResource,
        String packetTemplateResource,
        String skillSetResource,
        String mission,
        List<String> mustDo,
        List<String> mustNotDo,
        List<String> allowedInputs,
        String optimizationObjective,
        Map<String, Object> budget,
        ComparisonLens comparisonLens,
        GeospatialLens geospatialLens,
        String visibilityProfile,
        boolean multiPassEnabled,
        List<String> requiredAssessmentFields) {
}
