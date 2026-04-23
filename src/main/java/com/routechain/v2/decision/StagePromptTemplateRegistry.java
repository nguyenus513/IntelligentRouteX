package com.routechain.v2.decision;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class StagePromptTemplateRegistry {
    private final ObjectMapper objectMapper;
    private final String root;
    private final PromptSpecManifest manifest;
    private final Map<String, String> resourceCache = new LinkedHashMap<>();

    StagePromptTemplateRegistry(ObjectMapper objectMapper) {
        this(objectMapper, "prompts/decision/v2/");
    }

    StagePromptTemplateRegistry(ObjectMapper objectMapper, String root) {
        this.objectMapper = objectMapper;
        this.root = normalizeRoot(root);
        this.manifest = loadManifest();
        validateRequiredResources();
    }

    PromptSpecManifest manifest() {
        return manifest;
    }

    String loadGlobalPack(String name) {
        return loadResource(root + "global/" + name);
    }

    String loadSystemPrompt(String path) {
        return loadResource(root + path);
    }

    String loadPacketTemplate(String path) {
        return loadResource(root + path);
    }

    String loadSkillSet(String path) {
        if (path == null || path.isBlank()) {
            return "";
        }
        return loadResource(root + path);
    }

    String root() {
        return root;
    }

    private PromptSpecManifest loadManifest() {
        try {
            JsonNode node = objectMapper.readTree(loadResource(root + "prompt_spec_manifest.json"));
            String promptSpecVersion = requiredText(node, "promptSpecVersion");
            String packetTemplateVersion = requiredText(node, "packetTemplateVersion");
            String skillSetVersion = optionalText(node, "skillSetVersion");
            List<String> requiredGlobalPacks = iterableTexts(node.path("requiredGlobalPacks"));
            JsonNode stagesNode = node.path("stages");
            if (!stagesNode.isObject()) {
                throw new IllegalStateException("Prompt spec manifest missing stage mappings");
            }
            LinkedHashMap<String, PromptSpecManifest.StagePromptResourceEntry> mappings = new LinkedHashMap<>();
            stagesNode.fields().forEachRemaining(entry -> {
                JsonNode value = entry.getValue();
                mappings.put(entry.getKey(), new PromptSpecManifest.StagePromptResourceEntry(
                        requiredText(value, "systemPrompt"),
                        requiredText(value, "packetTemplate"),
                        optionalText(value, "skillSet")));
            });
            return new PromptSpecManifest(
                    promptSpecVersion,
                    packetTemplateVersion,
                    skillSetVersion,
                    List.copyOf(requiredGlobalPacks),
                    Map.copyOf(mappings));
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to parse prompt spec manifest", exception);
        }
    }

    private void validateRequiredResources() {
        for (String globalPack : manifest.requiredGlobalPacks()) {
            loadGlobalPack(globalPack);
        }
        for (PromptSpecManifest.StagePromptResourceEntry entry : manifest.stageMappings().values()) {
            loadSystemPrompt(entry.systemPrompt());
            loadPacketTemplate(entry.packetTemplate());
            if (entry.skillSet() != null && !entry.skillSet().isBlank()) {
                loadSkillSet(entry.skillSet());
            }
        }
    }

    private String loadResource(String path) {
        return resourceCache.computeIfAbsent(path, key -> {
            try (InputStream stream = Thread.currentThread().getContextClassLoader().getResourceAsStream(key)) {
                if (stream == null) {
                    throw new IllegalStateException("Missing prompt resource: " + key);
                }
                return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            } catch (IOException exception) {
                throw new IllegalStateException("Failed to load prompt resource " + key, exception);
            }
        });
    }

    private String requiredText(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual() || value.asText().isBlank()) {
            throw new IllegalStateException("Prompt spec manifest field is missing: " + field);
        }
        return value.asText();
    }

    private String optionalText(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isTextual() ? value.asText() : "";
    }

    private List<String> iterableTexts(JsonNode node) {
        if (!node.isArray()) {
            return List.of();
        }
        java.util.ArrayList<String> values = new java.util.ArrayList<>();
        for (JsonNode item : node) {
            if (item.isTextual() && !item.asText().isBlank()) {
                values.add(item.asText());
            }
        }
        return List.copyOf(values);
    }

    private String normalizeRoot(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Prompt registry root cannot be blank");
        }
        return value.endsWith("/") ? value : value + "/";
    }
}
