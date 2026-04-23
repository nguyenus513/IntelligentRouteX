package com.routechain.v2.decision;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class StageSkillRegistry {
    private final ObjectMapper objectMapper;
    private final StagePromptTemplateRegistry templateRegistry;
    private final Map<String, SkillSet> cache = new LinkedHashMap<>();

    StageSkillRegistry(ObjectMapper objectMapper, StagePromptTemplateRegistry templateRegistry) {
        this.objectMapper = objectMapper;
        this.templateRegistry = templateRegistry;
    }

    SkillSet load(StagePromptSpec spec) {
        String resource = spec.skillSetResource();
        if (resource == null || resource.isBlank()) {
            return SkillSet.empty(spec.skillSetVersion(), spec.stageName().wireName());
        }
        return cache.computeIfAbsent(resource, key -> parse(templateRegistry.loadSkillSet(key), spec));
    }

    private SkillSet parse(String raw, StagePromptSpec spec) {
        try {
            JsonNode root = objectMapper.readTree(raw);
            String stageName = requiredText(root, "stageName");
            if (!spec.stageName().wireName().equals(stageName)) {
                throw new IllegalStateException("Skill set stage mismatch for " + spec.stageName().wireName());
            }
            String version = requiredText(root, "skillSetVersion");
            JsonNode skillsNode = root.path("skills");
            if (!skillsNode.isArray()) {
                return SkillSet.empty(version, stageName);
            }
            List<SkillSpec> skills = new ArrayList<>();
            for (JsonNode skillNode : skillsNode) {
                skills.add(new SkillSpec(
                        requiredText(skillNode, "skillId"),
                        requiredText(skillNode, "description"),
                        texts(skillNode.path("requiredInputs")),
                        texts(skillNode.path("forbiddenAssumptions")),
                        texts(skillNode.path("outputEmphasis")),
                        texts(skillNode.path("recommendedReasonCodes")),
                        texts(skillNode.path("allowedToolIds"))));
            }
            return new SkillSet(version, stageName, List.copyOf(skills));
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to parse stage skill set for " + spec.stageName().wireName(), exception);
        }
    }

    private String requiredText(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual() || value.asText().isBlank()) {
            throw new IllegalStateException("Missing skill-set field: " + field);
        }
        return value.asText();
    }

    private List<String> texts(JsonNode node) {
        if (!node.isArray()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (JsonNode item : node) {
            if (item.isTextual() && !item.asText().isBlank()) {
                values.add(item.asText());
            }
        }
        return List.copyOf(values);
    }

    record SkillSet(
            String skillSetVersion,
            String stageName,
            List<SkillSpec> skills) {

        static SkillSet empty(String skillSetVersion, String stageName) {
            return new SkillSet(
                    skillSetVersion == null ? "" : skillSetVersion,
                    stageName == null ? "" : stageName,
                    List.of());
        }

        List<String> skillIds() {
            return skills.stream().map(SkillSpec::skillId).toList();
        }
    }
}
