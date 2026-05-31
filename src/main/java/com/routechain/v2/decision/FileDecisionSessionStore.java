package com.routechain.v2.decision;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.config.RouteChainDispatchV2Properties;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public final class FileDecisionSessionStore implements DecisionSessionStore {
    private final Path baseDirectory;
    private final Duration ttl;
    private final ObjectMapper objectMapper = JsonMapper.builder().findAndAddModules().build();

    public FileDecisionSessionStore(RouteChainDispatchV2Properties properties) {
        this.baseDirectory = Path.of(properties.getDecision().getLlm().getSessionStore().getBaseDir());
        this.ttl = properties.getDecision().getLlm().getSessionStore().getTtl();
    }

    @Override
    public boolean sessionStoreEnabled() {
        return true;
    }

    @Override
    public SessionStartResult beginSession(DecisionStageInputV1 input) {
        cleanupExpired();
        Path root = traceRoot(input);
        Path manifestPath = root.resolve("manifest.json");
        LinkedHashMap<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("schemaVersion", "decision-session-manifest/v1");
        manifest.put("traceId", input.traceId());
        manifest.put("runId", input.runId());
        manifest.put("tickId", input.tickId());
        manifest.put("startedAt", Instant.now());
        manifest.put("promptFamily", "v3");
        manifest.put("sessionNamespace", sessionNamespace(input));
        boolean created = !Files.exists(manifestPath);
        try {
            Files.createDirectories(root);
            if (created) {
                objectMapper.writeValue(manifestPath.toFile(), manifest);
            } else {
                manifest = objectMapper.readValue(manifestPath.toFile(), LinkedHashMap.class);
            }
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to initialize decision session store", exception);
        }
        return new SessionStartResult(created, Map.copyOf(manifest));
    }

    @Override
    public SessionContext resolveContext(DecisionStageInputV1 input) {
        if (input.upstreamRefs().isEmpty()) {
            return SessionContext.empty();
        }
        List<Map<String, Object>> priorStageRefs = new ArrayList<>();
        List<String> routeVectorRefs = new ArrayList<>();
        List<String> tileContextRefs = new ArrayList<>();
        List<String> selectedCandidateRefs = new ArrayList<>();
        List<String> critiqueRefs = new ArrayList<>();
        List<String> readRefs = new ArrayList<>();
        for (String upstreamRef : input.upstreamRefs()) {
            Path stageRoot = traceRoot(input).resolve(sanitize(upstreamRef));
            Path summaryPath = stageRoot.resolve("stage_summary.json");
            Path refsPath = stageRoot.resolve("stage_refs.json");
            Path resultPath = stageRoot.resolve("stage_result.json");
            if (!Files.exists(summaryPath) && !Files.exists(refsPath) && !Files.exists(resultPath)) {
                continue;
            }
            readRefs.add("stage:" + upstreamRef);
            LinkedHashMap<String, Object> stageRef = new LinkedHashMap<>();
            stageRef.put("stageName", upstreamRef);
            stageRef.put("summaryPath", summaryPath.toString());
            stageRef.put("refsPath", refsPath.toString());
            stageRef.put("resultPath", resultPath.toString());
            Map<String, Object> summary = readMap(summaryPath);
            if (!summary.isEmpty()) {
                stageRef.put("summary", summary);
            }
            Map<String, Object> refs = readMap(refsPath);
            if (!refs.isEmpty()) {
                stageRef.put("refs", refs);
                routeVectorRefs.addAll(textList(refs.get("routeVectorRefs")));
                tileContextRefs.addAll(textList(refs.get("tileContextRefs")));
                selectedCandidateRefs.addAll(textList(refs.get("selectedCandidateRefs")));
                critiqueRefs.addAll(textList(refs.get("critiqueRefs")));
            }
            for (String writeRef : textList(summary.get("sessionWriteRefs"))) {
                if (writeRef.startsWith("route-vector:")) {
                    routeVectorRefs.add(writeRef.substring("route-vector:".length()));
                } else if (writeRef.startsWith("tile-context:")) {
                    tileContextRefs.add(writeRef.substring("tile-context:".length()));
                } else if (writeRef.startsWith("selected-candidate:")) {
                    selectedCandidateRefs.add(writeRef.substring("selected-candidate:".length()));
                } else if (writeRef.startsWith("critique:")) {
                    critiqueRefs.add(writeRef.substring("critique:".length()));
                }
            }
            if (routeVectorRefs.isEmpty()
                    && tileContextRefs.isEmpty()
                    && selectedCandidateRefs.isEmpty()
                    && critiqueRefs.isEmpty()) {
                routeVectorRefs.add(upstreamRef);
                tileContextRefs.add(upstreamRef);
                selectedCandidateRefs.add(upstreamRef);
                critiqueRefs.add(upstreamRef);
            }
            priorStageRefs.add(Map.copyOf(stageRef));
        }
        routeVectorRefs.forEach(ref -> readRefs.add("route-vector:" + ref));
        tileContextRefs.forEach(ref -> readRefs.add("tile-context:" + ref));
        selectedCandidateRefs.forEach(ref -> readRefs.add("selected-candidate:" + ref));
        critiqueRefs.forEach(ref -> readRefs.add("critique:" + ref));
        Map<String, Object> sessionRefs = Map.of(
                "priorStageResultRefs", List.copyOf(priorStageRefs),
                "routeVectorRefs", List.copyOf(routeVectorRefs.stream().distinct().toList()),
                "tileContextRefs", List.copyOf(tileContextRefs.stream().distinct().toList()),
                "selectedCandidateRefs", List.copyOf(selectedCandidateRefs.stream().distinct().toList()),
                "critiqueRefs", List.copyOf(critiqueRefs.stream().distinct().toList()));
        int sessionRefCount = priorStageRefs.size()
                + routeVectorRefs.size()
                + tileContextRefs.size()
                + selectedCandidateRefs.size()
                + critiqueRefs.size();
        return new SessionContext(
                sessionRefs,
                sessionRefCount,
                sessionNamespace(input),
                List.copyOf(readRefs.stream().distinct().toList()));
    }

    @Override
    public void recordPass(DecisionStageInputV1 input,
                           String passType,
                           PromptPackRegistry.RenderedPrompt renderedPrompt,
                           NineRouterResponsesClient.LlmInvocationResult result) {
        Path passRoot = stageRoot(input).resolve("passes");
        Path rawRoot = stageRoot(input).resolve("raw");
        LinkedHashMap<String, Object> summary = new LinkedHashMap<>();
        summary.put("schemaVersion", "decision-session-pass-summary/v1");
        summary.put("traceId", input.traceId());
        summary.put("stageName", input.stageName().wireName());
        summary.put("passType", passType);
        summary.put("promptMetadata", renderedPrompt.metadata());
        summary.put("selectedIds", result.parsedOutput().getOrDefault("selectedIds", List.of()));
        summary.put("tokenUsage", result.tokenUsage());
        summary.put("retryCount", result.retryCount());
        summary.put("rawResponseHash", result.rawResponseHash());
        writeJson(passRoot.resolve(sanitize(passType) + ".json"), summary);
        if (result.rawResponseBody() != null && !result.rawResponseBody().isBlank()) {
            writeJson(rawRoot.resolve(sanitize(passType) + "-provider-response.json"), Map.of(
                    "schemaVersion", "decision-session-raw-provider-response/v1",
                    "traceId", input.traceId(),
                    "stageName", input.stageName().wireName(),
                    "passType", passType,
                    "providerModel", result.providerModel(),
                    "rawResponseBody", result.rawResponseBody()));
        }
    }

    @Override
    public StageSessionRecord recordStageResult(DecisionStageInputV1 input,
                                                DecisionStageOutputV1 output,
                                                List<Map<String, Object>> passSummaries) {
        Path stageRoot = stageRoot(input);
        LinkedHashMap<String, Object> stageSummary = new LinkedHashMap<>();
        stageSummary.put("schemaVersion", "decision-session-stage-summary/v1");
        stageSummary.put("traceId", input.traceId());
        stageSummary.put("runId", input.runId());
        stageSummary.put("tickId", input.tickId());
        stageSummary.put("stageName", input.stageName().wireName());
        stageSummary.put("selectedIds", output.selectedIds());
        stageSummary.put("confidence", output.meta().confidence());
        stageSummary.put("candidateCountSeen", output.assessments().containsKey("items")
                && output.assessments().get("items") instanceof List<?> items ? items.size() : 0);
        stageSummary.put("decisionQualityFlags", output.meta().decisionQualityFlags());
        stageSummary.put("passCount", passSummaries == null ? 0 : passSummaries.size());
        stageSummary.put("fallbackUsed", output.meta().fallbackUsed());
        stageSummary.put("fallbackReason", output.meta().fallbackReason() == null ? "" : output.meta().fallbackReason());
        stageSummary.put("sessionNamespace", sessionNamespace(input));

        LinkedHashMap<String, Object> stageRefs = new LinkedHashMap<>();
        stageRefs.put("schemaVersion", "decision-session-stage-refs/v1");
        stageRefs.put("traceId", input.traceId());
        stageRefs.put("stageName", input.stageName().wireName());
        stageRefs.put("selectedCandidateRefs", output.selectedIds());
        stageRefs.put("routeVectorRefs", routeVectorRefs(output.assessments(), output.selectedIds()));
        stageRefs.put("tileContextRefs", tileContextRefs(input.geospatialContext()));
        stageRefs.put("critiqueRefs", critiqueRefs(output.assessments()));
        List<String> writeRefs = sessionWriteRefs(stageRefs);
        stageSummary.put("sessionWriteRefs", writeRefs);

        writeJson(stageRoot.resolve("stage_summary.json"), stageSummary);
        writeJson(stageRoot.resolve("stage_refs.json"), stageRefs);
        writeJson(stageRoot.resolve("stage_result.json"), Map.of(
                "schemaVersion", "decision-session-stage-result/v1",
                "traceId", input.traceId(),
                "stageName", input.stageName().wireName(),
                "output", output,
                "passSummaries", passSummaries == null ? List.of() : passSummaries));
        return new StageSessionRecord(Map.copyOf(stageSummary), Map.copyOf(stageRefs), sessionNamespace(input), writeRefs);
    }

    private Path traceRoot(DecisionStageInputV1 input) {
        return baseDirectory
                .resolve(sanitize(input.runId()))
                .resolve(sanitize(input.tickId()))
                .resolve(sanitize(input.traceId()));
    }

    private Path stageRoot(DecisionStageInputV1 input) {
        return traceRoot(input).resolve(sanitize(input.stageName().wireName()));
    }

    private String sessionNamespace(DecisionStageInputV1 input) {
        return sanitize(input.runId()) + "/" + sanitize(input.tickId()) + "/" + sanitize(input.traceId());
    }

    private void writeJson(Path path, Object payload) {
        try {
            Files.createDirectories(path.getParent());
            objectMapper.writeValue(path.toFile(), payload);
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to write decision session artifact " + path, exception);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readMap(Path path) {
        if (path == null || !Files.exists(path)) {
            return Map.of();
        }
        try {
            return objectMapper.readValue(path.toFile(), LinkedHashMap.class);
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to read decision session artifact " + path, exception);
        }
    }

    @SuppressWarnings("unchecked")
    private List<String> textList(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream().map(String::valueOf).toList();
    }

    private List<String> routeVectorRefs(Map<String, Object> assessments, List<String> selectedIds) {
        Object rawItems = assessments.get("items");
        if (!(rawItems instanceof List<?> items)) {
            return selectedIds == null ? List.of() : selectedIds;
        }
        List<String> refs = items.stream()
                .filter(Map.class::isInstance)
                .map(Map.class::cast)
                .flatMap(item -> textList(item.get("routeVectorRefs")).stream())
                .distinct()
                .toList();
        return refs.isEmpty() && selectedIds != null ? selectedIds : refs;
    }

    private List<String> critiqueRefs(Map<String, Object> assessments) {
        Object rawItems = assessments.get("items");
        if (!(rawItems instanceof List<?> items)) {
            return List.of();
        }
        List<String> refs = items.stream()
                .filter(Map.class::isInstance)
                .map(Map.class::cast)
                .flatMap(item -> textList(item.get("dominanceReasonCodes")).stream())
                .distinct()
                .toList();
        if (!refs.isEmpty()) {
            return refs;
        }
        return textList(assessments.get("reasonCodes")).stream().distinct().toList();
    }

    private List<String> sessionWriteRefs(Map<String, Object> stageRefs) {
        List<String> refs = new ArrayList<>();
        textList(stageRefs.get("selectedCandidateRefs")).forEach(ref -> refs.add("selected-candidate:" + ref));
        textList(stageRefs.get("routeVectorRefs")).forEach(ref -> refs.add("route-vector:" + ref));
        textList(stageRefs.get("tileContextRefs")).forEach(ref -> refs.add("tile-context:" + ref));
        textList(stageRefs.get("critiqueRefs")).forEach(ref -> refs.add("critique:" + ref));
        return List.copyOf(refs.stream().distinct().toList());
    }

    @SuppressWarnings("unchecked")
    private List<String> tileContextRefs(Map<String, Object> geospatialContext) {
        List<String> refs = new ArrayList<>();
        Object selectedTiles = geospatialContext.get("selectedTiles");
        if (selectedTiles instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?> map && map.get("tileId") != null) {
                    refs.add(String.valueOf(map.get("tileId")));
                } else {
                    refs.add(String.valueOf(item));
                }
            }
        }
        Object summaries = geospatialContext.get("tileContextSummaries");
        if (summaries instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?> map && map.get("tileId") != null) {
                    refs.add(String.valueOf(map.get("tileId")));
                }
            }
        }
        return refs.stream().distinct().toList();
    }

    private void cleanupExpired() {
        if (!Files.exists(baseDirectory)) {
            return;
        }
        Instant cutoff = Instant.now().minus(ttl == null ? Duration.ofMinutes(10) : ttl);
        try (Stream<Path> runs = Files.list(baseDirectory)) {
            runs.forEach(runRoot -> deleteIfExpired(runRoot, cutoff));
        } catch (IOException ignored) {
        }
    }

    private void deleteIfExpired(Path root, Instant cutoff) {
        try {
            Instant modified = Files.getLastModifiedTime(root).toInstant();
            if (modified.isBefore(cutoff)) {
                try (Stream<Path> stream = Files.walk(root)) {
                    stream.sorted((left, right) -> right.getNameCount() - left.getNameCount())
                            .forEach(path -> {
                                try {
                                    Files.deleteIfExists(path);
                                } catch (IOException ignored) {
                                }
                            });
                }
            }
        } catch (IOException ignored) {
        }
    }

    private String sanitize(String raw) {
        return raw == null || raw.isBlank() ? "unknown" : raw.replaceAll("[^a-zA-Z0-9._-]", "_");
    }
}
