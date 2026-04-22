package com.routechain.v2.decision;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class PromptPackRegistry {
    private final ObjectMapper objectMapper;
    private final StagePromptTemplateRegistry templateRegistry;
    private final StagePacketBuilder packetBuilder;

    public PromptPackRegistry(ObjectMapper objectMapper) {
        this(objectMapper, new StagePromptTemplateRegistry(objectMapper), new StagePacketBuilder());
    }

    PromptPackRegistry(ObjectMapper objectMapper,
                       StagePromptTemplateRegistry templateRegistry,
                       StagePacketBuilder packetBuilder) {
        this.objectMapper = objectMapper;
        this.templateRegistry = templateRegistry;
        this.packetBuilder = packetBuilder;
    }

    public String renderSystemPrompt(DecisionStageInputV1 input) {
        return renderPrompt(input).systemPrompt();
    }

    public String renderDynamicPrompt(DecisionStageInputV1 input) {
        return renderPrompt(input).dynamicPrompt();
    }

    public RenderedPrompt renderPrompt(DecisionStageInputV1 input) {
        try {
            StagePromptSpec spec = packetBuilder.stageSpec(templateRegistry.manifest(), input.stageName());
            StagePacketBuilder.StagePacketBuildResult packetResult = packetBuilder.build(input, spec);
            String systemPrompt = renderSystem(spec);
            String packetTemplate = templateRegistry.loadPacketTemplate(spec.packetTemplateResource());
            String dynamicPrompt = renderTemplate(packetTemplate, packetVariables(packetResult.packet()));
            LinkedHashMap<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("promptSpecVersion", spec.promptSpecVersion());
            metadata.put("stagePromptName", spec.stagePromptName());
            metadata.put("stagePromptChecksum", checksum(systemPrompt));
            metadata.put("packetTemplateVersion", spec.packetTemplateVersion());
            metadata.put("packetTemplateChecksum", checksum(packetTemplate));
            metadata.put("mission", spec.mission());
            metadata.put("budgetApplied", packetResult.packet().get("budget"));
            metadata.put("candidateCountSeen", packetResult.candidateCountSeen());
            metadata.put("comparisonPackCoverage", packetResult.comparisonPackCoverage());
            metadata.put("geospatialCoverage", packetResult.geospatialCoverage());
            metadata.put("missingContextFlags", packetResult.missingContextFlags());
            metadata.put("comparisonLens", spec.comparisonLens().name());
            metadata.put("geospatialLens", spec.geospatialLens().name());
            metadata.put("visibilityProfile", spec.visibilityProfile());
            metadata.put("allowedInputs", spec.allowedInputs());
            metadata.put("multiPassEnabled", spec.multiPassEnabled());
            metadata.put("fallbackReason", "");
            return new RenderedPrompt(systemPrompt, dynamicPrompt, spec, packetResult.packet(), Map.copyOf(metadata));
        } catch (RuntimeException exception) {
            return genericFallback(input, exception.getMessage() == null ? "prompt-spec-render-failed" : exception.getMessage());
        }
    }

    public Map<String, Object> outputContractMetadata() {
        return Map.of(
                "globalPack", templateRegistry.manifest().requiredGlobalPacks(),
                "requiredAssessmentFields", List.of(
                        "id",
                        "score",
                        "rank",
                        "selected",
                        "confidence",
                        "reasonCodes",
                        "dominanceReasonCodes",
                        "regretToBestAlternative",
                        "driverFitSummary",
                        "routeVectorRefs",
                        "geospatialFlags",
                        "burstSensitivityFlags",
                        "rationale"));
    }

    private String renderSystem(StagePromptSpec spec) {
        List<String> sections = new ArrayList<>();
        for (String globalPack : templateRegistry.manifest().requiredGlobalPacks()) {
            sections.add(templateRegistry.loadGlobalPack(globalPack).trim());
        }
        String systemTemplate = templateRegistry.loadSystemPrompt(spec.systemPromptResource());
        sections.add(renderTemplate(systemTemplate, Map.of(
                "stageName", spec.stageName().wireName(),
                "mission", spec.mission(),
                "mustDo", spec.mustDo(),
                "mustNotDo", spec.mustNotDo(),
                "allowedInputs", spec.allowedInputs(),
                "optimizationObjective", spec.optimizationObjective(),
                "budget", spec.budget(),
                "comparisonLens", spec.comparisonLens().name(),
                "geospatialLens", spec.geospatialLens().name(),
                "requiredAssessmentFields", spec.requiredAssessmentFields())));
        return String.join("\n\n", sections);
    }

    private Map<String, Object> packetVariables(Map<String, Object> packet) {
        LinkedHashMap<String, Object> variables = new LinkedHashMap<>(packet);
        variables.put("packetJson", packet);
        return Map.copyOf(variables);
    }

    private String renderTemplate(String template, Map<String, Object> variables) {
        String rendered = template;
        for (Map.Entry<String, Object> entry : variables.entrySet()) {
            rendered = rendered.replace("{{" + entry.getKey() + "}}", serialize(entry.getValue()));
        }
        return rendered;
    }

    private RenderedPrompt genericFallback(DecisionStageInputV1 input, String fallbackReason) {
        String systemPrompt = genericSystemPrompt(input);
        String dynamicPrompt = genericDynamicPrompt(input);
        LinkedHashMap<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("promptSpecVersion", "generic-fallback/v1");
        metadata.put("stagePromptName", input.stageName().wireName());
        metadata.put("stagePromptChecksum", checksum(systemPrompt));
        metadata.put("packetTemplateVersion", "generic-fallback/v1");
        metadata.put("packetTemplateChecksum", checksum(dynamicPrompt));
        metadata.put("mission", "fallback generic prompt for " + input.stageName().wireName());
        metadata.put("budgetApplied", input.constraints().getOrDefault("contextBudget", Map.of()));
        metadata.put("candidateCountSeen", countGenericCandidates(input));
        metadata.put("comparisonPackCoverage", input.comparisonPack().isEmpty() ? 0.0 : 1.0);
        metadata.put("geospatialCoverage", input.geospatialContext().isEmpty() ? 0.0 : 1.0);
        metadata.put("missingContextFlags", List.of("prompt-spec-fallback"));
        metadata.put("comparisonLens", "generic");
        metadata.put("geospatialLens", "generic");
        metadata.put("visibilityProfile", "generic-fallback");
        metadata.put("allowedInputs", List.of("dispatchContext", "candidateSet", "referenceFrame", "comparisonPack", "geospatialContext", "burstContext", "upstreamSummary"));
        metadata.put("multiPassEnabled", false);
        metadata.put("fallbackReason", fallbackReason);
        return new RenderedPrompt(
                systemPrompt,
                dynamicPrompt,
                null,
                Map.of("schemaVersion", "decision-stage-packet/v2", "stageName", input.stageName().wireName()),
                Map.copyOf(metadata));
    }

    private String genericSystemPrompt(DecisionStageInputV1 input) {
        List<String> lines = new ArrayList<>();
        lines.add("Return strict JSON only.");
        lines.add("Do not invent ids outside the candidate window.");
        lines.add("Use the provided world state, reference frame, comparison pack, geospatial context, burst context, and upstream summaries only.");
        lines.add("Generic fallback prompt is active.");
        lines.add("Stage name: " + input.stageName().wireName() + ".");
        lines.add("Output contract: selectedIds plus assessments.");
        return String.join("\n", lines);
    }

    private String genericDynamicPrompt(DecisionStageInputV1 input) {
        LinkedHashMap<String, Object> stagePacket = new LinkedHashMap<>();
        stagePacket.put("dispatchContext", input.dispatchContext());
        stagePacket.put("candidateWindow", input.candidateSet());
        stagePacket.put("referenceFrame", input.referenceFrame());
        stagePacket.put("comparisonPack", input.comparisonPack());
        stagePacket.put("geospatialContext", input.geospatialContext());
        stagePacket.put("burstContext", input.burstContext());
        stagePacket.put("upstreamSummary", input.upstreamSummary());
        stagePacket.put("constraints", input.constraints());
        stagePacket.put("contextSelection", input.contextSelection());
        stagePacket.put("objectiveWeights", input.objectiveWeights());
        stagePacket.put("upstreamRefs", input.upstreamRefs());
        return serialize(stagePacket);
    }

    private int countGenericCandidates(DecisionStageInputV1 input) {
        Object raw = input.candidateSet().get("window");
        return raw instanceof List<?> list ? list.size() : 0;
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Failed to serialize prompt pack payload", exception);
        }
    }

    private String checksum(String content) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(content.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 not available", exception);
        }
    }

    public record RenderedPrompt(
            String systemPrompt,
            String dynamicPrompt,
            StagePromptSpec stageSpec,
            Map<String, Object> packet,
            Map<String, Object> metadata) {
    }
}
