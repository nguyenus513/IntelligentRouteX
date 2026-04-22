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
    private static final String ROOT = "prompts/decision/v2/";

    private final ObjectMapper objectMapper;
    private final PromptSpecManifest manifest;
    private final Map<String, String> resourceCache = new LinkedHashMap<>();

    StagePromptTemplateRegistry(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.manifest = loadManifest();
        validateRequiredResources();
    }

    PromptSpecManifest manifest() {
        return manifest;
    }

    String loadGlobalPack(String name) {
        return loadResource(ROOT + "global/" + name);
    }

    String loadSystemPrompt(String path) {
        return loadResource(ROOT + path);
    }

    String loadPacketTemplate(String path) {
        return loadResource(ROOT + path);
    }

    private PromptSpecManifest loadManifest() {
        try {
            JsonNode node = objectMapper.readTree(loadResource(ROOT + "prompt_spec_manifest.json"));
            String promptSpecVersion = requiredText(node, "promptSpecVersion");
            String packetTemplateVersion = requiredText(node, "packetTemplateVersion");
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
                        requiredText(value, "packetTemplate")));
            });
            return new PromptSpecManifest(
                    promptSpecVersion,
                    packetTemplateVersion,
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
}
