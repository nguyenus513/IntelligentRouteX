package com.routechain.v2.decision;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.config.RouteChainDispatchV2Properties;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class NineRouterResponsesClient {
    private final RouteChainDispatchV2Properties.Llm properties;
    private final ResponsesTransport transport;
    private final ObjectMapper objectMapper;
    private final PromptPackRegistry promptPackRegistry;
    private volatile ModelResolution cachedModelResolution;

    public NineRouterResponsesClient(RouteChainDispatchV2Properties.Llm properties) {
        this(properties, new NoOpDecisionSessionStore());
    }

    public NineRouterResponsesClient(RouteChainDispatchV2Properties.Llm properties,
                                     DecisionSessionStore decisionSessionStore) {
        this(properties, new DefaultResponsesTransport(), JsonMapper.builder().findAndAddModules().build(), decisionSessionStore);
    }

    NineRouterResponsesClient(RouteChainDispatchV2Properties.Llm properties,
                              ResponsesTransport transport,
                              ObjectMapper objectMapper) {
        this(properties, transport, objectMapper, new NoOpDecisionSessionStore());
    }

    NineRouterResponsesClient(RouteChainDispatchV2Properties.Llm properties,
                              ResponsesTransport transport,
                              ObjectMapper objectMapper,
                              DecisionSessionStore decisionSessionStore) {
        this.properties = properties;
        this.transport = transport;
        this.objectMapper = objectMapper;
        this.promptPackRegistry = new PromptPackRegistry(objectMapper, properties, decisionSessionStore);
    }

    public RuntimeConfiguration runtimeConfiguration() {
        return new RuntimeConfiguration(
                configuredValue(
                        "routechain.dispatch-v2.decision.llm.base-url",
                        "ROUTECHAIN_DECISION_LLM_BASE_URL",
                        properties.getBaseUrl()),
                configuredValue(
                        "routechain.dispatch-v2.decision.llm.model",
                        "ROUTECHAIN_DECISION_LLM_MODEL",
                        properties.getModel()),
                properties.getWireApi(),
                properties.getProvider());
    }

    public LlmInvocationResult invoke(DecisionStageInputV1 input, DecisionEffort requestedEffort) {
        return invoke(input, requestedEffort, promptPackRegistry.renderPrompt(input));
    }

    LlmInvocationResult invoke(DecisionStageInputV1 input,
                               DecisionEffort requestedEffort,
                               PromptPackRegistry.RenderedPrompt renderedPrompt) {
        String apiKey = System.getenv(properties.getApiKeyEnv());
        if (apiKey == null || apiKey.isBlank()) {
            throw failure("llm-api-key-missing", Map.of(
                    "apiKeyEnv", properties.getApiKeyEnv()));
        }
        RuntimeConfiguration runtimeConfiguration = runtimeConfiguration();
        ModelResolution modelResolution = resolveModel(runtimeConfiguration.baseUrl(), apiKey, runtimeConfiguration.configuredModelFamily());
        DecisionEffort appliedEffort = requestedEffort == null ? DecisionEffort.MEDIUM : requestedEffort;
        Duration requestTimeout = requestTimeout(input.stageName(), requestedEffort);
        int retryCount = 0;
        int maxAttempts = Math.max(1, properties.getMaxRetries() + 1);
        String lastFailureReason = "provider-empty-response";
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            JsonNode requestBody = buildRequestBody(renderedPrompt, input.stageName(), appliedEffort, modelResolution.resolvedModelId());
            try {
                TransportResponse response = transport.post(
                        runtimeConfiguration.baseUrl(),
                        apiKey,
                        requestTimeout,
                        requestBody,
                        objectMapper);
                if (response.statusCode() >= 400) {
                    String failureReason = classifyHttpFailure(response.statusCode(), response.body());
                    if ("provider-rejected-effort".equals(failureReason)
                            && requestedEffort == DecisionEffort.XHIGH
                            && appliedEffort == DecisionEffort.XHIGH) {
                        appliedEffort = DecisionEffort.HIGH;
                        retryCount++;
                        lastFailureReason = failureReason;
                        continue;
                    }
                    if (attempt >= maxAttempts) {
                        throw failure(failureReason, Map.of(
                                "configuredModelFamily", modelResolution.configuredModelFamily(),
                                "resolvedModelId", modelResolution.resolvedModelId(),
                                "providerBaseUrl", runtimeConfiguration.baseUrl(),
                                "providerWireApi", runtimeConfiguration.wireApi(),
                                "modelDiscoverySource", modelResolution.discoverySource()));
                    }
                    retryCount++;
                    lastFailureReason = failureReason;
                    continue;
                }
                return parseResponse(response.body(), requestedEffort, appliedEffort, retryCount, modelResolution, runtimeConfiguration);
            } catch (NineRouterClientException exception) {
                String failureReason = exception.failureReason();
                if (attempt >= maxAttempts || !retryable(failureReason)) {
                    throw exception;
                }
                retryCount++;
                lastFailureReason = failureReason;
            } catch (IllegalStateException exception) {
                String failureReason = exception.getMessage() == null ? "provider-http-error" : exception.getMessage();
                if (attempt >= maxAttempts || !retryable(failureReason)) {
                    throw failure(failureReason, Map.of(
                            "configuredModelFamily", modelResolution.configuredModelFamily(),
                            "resolvedModelId", modelResolution.resolvedModelId(),
                            "providerBaseUrl", runtimeConfiguration.baseUrl(),
                            "providerWireApi", runtimeConfiguration.wireApi(),
                            "modelDiscoverySource", modelResolution.discoverySource()), exception);
                }
                retryCount++;
                lastFailureReason = failureReason;
            }
        }
        throw failure(lastFailureReason, Map.of(
                "configuredModelFamily", modelResolution.configuredModelFamily(),
                "resolvedModelId", modelResolution.resolvedModelId(),
                "providerBaseUrl", runtimeConfiguration.baseUrl(),
                "providerWireApi", runtimeConfiguration.wireApi(),
                "modelDiscoverySource", modelResolution.discoverySource()));
    }

    private Duration requestTimeout(DecisionStageName stageName, DecisionEffort requestedEffort) {
        Duration configuredTimeout = properties.getTimeoutMs();
        if (configuredTimeout == null || configuredTimeout.isNegative() || configuredTimeout.isZero()) {
            configuredTimeout = Duration.ofSeconds(45);
        }
        DecisionEffort effectiveEffort = requestedEffort == null ? DecisionEffort.MEDIUM : requestedEffort;
        return switch (effectiveEffort) {
            case MEDIUM -> configuredTimeout;
            case HIGH -> configuredTimeout.multipliedBy(2);
            case XHIGH -> {
                Duration boosted = configuredTimeout.multipliedBy(3);
                if (stageName == DecisionStageName.ROUTE_GENERATION || stageName == DecisionStageName.FINAL_SELECTION) {
                    yield boosted.compareTo(Duration.ofSeconds(90)) < 0 ? Duration.ofSeconds(90) : boosted;
                }
                yield boosted;
            }
        };
    }

    private JsonNode buildRequestBody(PromptPackRegistry.RenderedPrompt renderedPrompt,
                                      DecisionStageName stageName,
                                      DecisionEffort appliedEffort,
                                      String model) {
        Map<String, Object> body = new LinkedHashMap<>();
        java.util.List<Map<String, Object>> contentItems = java.util.List.of(
                Map.of(
                        "role", "system",
                        "content", java.util.List.of(Map.of(
                                "type", "input_text",
                                "text", renderedPrompt.systemPrompt()))),
                Map.of(
                        "role", "user",
                        "content", java.util.List.of(Map.of(
                                "type", "input_text",
                                "text", renderedPrompt.dynamicPrompt()))));
        body.put("model", model);
        body.put("parallel_tool_calls", properties.isParallelToolCalls());
        body.put("reasoning", Map.of("effort", appliedEffort.wireValue()));
        body.put("text", Map.of(
                "format", Map.of(
                        "type", "json_schema",
                        "name", "stage_output_v1",
                        "strict", properties.isStrictStructuredOutputs(),
                        "schema", outputSchema(stageName))));
        body.put("input", contentItems);
        return objectMapper.valueToTree(body);
    }

    private Map<String, Object> outputSchema(DecisionStageName stageName) {
        return Map.of(
                "type", "object",
                "additionalProperties", false,
                "properties", Map.of(
                        "selectedIds", Map.of("type", "array", "items", Map.of("type", "string")),
                        "assessments", Map.of(
                                "type", "object",
                                "additionalProperties", false,
                                "properties", Map.of(
                                        "summary", Map.of("type", "string"),
                                        "reasonCodes", Map.of("type", "array", "items", Map.of("type", "string")),
                                        "items", Map.of(
                                                "type", "array",
                                                "items", Map.of(
                                                        "type", "object",
                                                        "additionalProperties", false,
                                "properties", Map.ofEntries(
                                        Map.entry("id", Map.of("type", "string")),
                                        Map.entry("score", Map.of("type", "number")),
                                        Map.entry("rank", Map.of("type", "integer")),
                                        Map.entry("selected", Map.of("type", "boolean")),
                                        Map.entry("confidence", Map.of("type", "number")),
                                        Map.entry("reasonCodes", Map.of("type", "array", "items", Map.of("type", "string"))),
                                        Map.entry("dominanceReasonCodes", Map.of("type", "array", "items", Map.of("type", "string"))),
                                        Map.entry("regretToBestAlternative", Map.of("type", "number")),
                                        Map.entry("driverFitSummary", Map.of("type", "string")),
                                        Map.entry("routeVectorRefs", Map.of("type", "array", "items", Map.of("type", "string"))),
                                        Map.entry("geospatialFlags", Map.of("type", "array", "items", Map.of("type", "string"))),
                                        Map.entry("burstSensitivityFlags", Map.of("type", "array", "items", Map.of("type", "string"))),
                                        Map.entry("rationale", Map.of("type", "string"))),
                                                        "required", java.util.List.of(
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
                                                                "rationale")))),
                                "required", java.util.List.of("summary", "reasonCodes", "items"))),
                "required", java.util.List.of("selectedIds", "assessments"));
    }

    private LlmInvocationResult parseResponse(String body,
                                              DecisionEffort requestedEffort,
                                              DecisionEffort appliedEffort,
                                              int retryCount,
                                              ModelResolution modelResolution,
                                              RuntimeConfiguration runtimeConfiguration) {
        try {
            if (body == null || body.isBlank()) {
                throw failure("provider-empty-response", Map.of(
                        "configuredModelFamily", modelResolution.configuredModelFamily(),
                        "resolvedModelId", modelResolution.resolvedModelId(),
                        "providerBaseUrl", runtimeConfiguration.baseUrl(),
                        "providerWireApi", runtimeConfiguration.wireApi(),
                        "modelDiscoverySource", modelResolution.discoverySource()));
            }
            JsonNode node = objectMapper.readTree(body);
            JsonNode usage = node.path("usage");
            Map<String, Object> tokenUsage = usage.isObject()
                    ? objectMapper.convertValue(usage, new TypeReference<>() {
                    })
                    : Map.of();
            JsonNode outputNode = firstOutputNode(node);
            Map<String, Object> parsedOutput = validateParsedOutput(outputNode);
            tokenUsage = normalizeTokenUsage(tokenUsage);
            return new LlmInvocationResult(
                    parsedOutput,
                    requestedEffort.wireValue(),
                    appliedEffort.wireValue(),
                    tokenUsage,
                    retryCount,
                    sha256(body),
                    body,
                    modelResolution.resolvedModelId(),
                    modelResolution.configuredModelFamily(),
                    runtimeConfiguration.baseUrl(),
                    runtimeConfiguration.wireApi(),
                    modelResolution.discoverySource());
        } catch (IOException exception) {
            throw failure("provider-invalid-json", Map.of(
                    "configuredModelFamily", modelResolution.configuredModelFamily(),
                    "resolvedModelId", modelResolution.resolvedModelId(),
                    "providerBaseUrl", runtimeConfiguration.baseUrl(),
                    "providerWireApi", runtimeConfiguration.wireApi(),
                    "modelDiscoverySource", modelResolution.discoverySource()), exception);
        }
    }

    private JsonNode firstOutputNode(JsonNode root) {
        JsonNode output = root.path("output");
        if (!output.isArray()) {
            return objectMapper.createObjectNode();
        }
        for (JsonNode item : output) {
            JsonNode content = item.path("content");
            if (!content.isArray()) {
                continue;
            }
            for (JsonNode contentItem : content) {
                JsonNode text = contentItem.path("text");
                if (!text.isTextual()) {
                    continue;
                }
                try {
                    return objectMapper.readTree(text.asText());
                } catch (IOException ignored) {
                    throw new IllegalStateException("provider-invalid-json");
                }
            }
        }
        throw new IllegalStateException("provider-empty-response");
    }

    private Map<String, Object> validateParsedOutput(JsonNode outputNode) {
        if (!outputNode.isObject()) {
            throw new IllegalStateException("provider-schema-invalid");
        }
        JsonNode selectedIds = outputNode.get("selectedIds");
        JsonNode assessments = outputNode.get("assessments");
        if (selectedIds == null || !selectedIds.isArray() || assessments == null || !assessments.isObject()) {
            throw new IllegalStateException("provider-schema-invalid");
        }
        JsonNode items = assessments.get("items");
        if (items == null || !items.isArray()) {
            throw new IllegalStateException("provider-schema-invalid");
        }
        for (JsonNode item : items) {
            if (!item.isObject()
                    || !item.hasNonNull("id")
                    || !item.hasNonNull("score")
                    || !item.hasNonNull("rank")
                    || !item.hasNonNull("selected")
                    || !item.hasNonNull("confidence")
                    || !item.hasNonNull("reasonCodes")
                    || !item.hasNonNull("dominanceReasonCodes")
                    || !item.hasNonNull("regretToBestAlternative")
                    || !item.hasNonNull("driverFitSummary")
                    || !item.hasNonNull("routeVectorRefs")
                    || !item.hasNonNull("geospatialFlags")
                    || !item.hasNonNull("burstSensitivityFlags")
                    || !item.hasNonNull("rationale")) {
                throw new IllegalStateException("provider-schema-invalid");
            }
        }
        return objectMapper.convertValue(outputNode, new TypeReference<>() {
        });
    }

    private Map<String, Object> normalizeTokenUsage(Map<String, Object> tokenUsage) {
        if (tokenUsage == null || tokenUsage.isEmpty()) {
            return Map.of();
        }
        long inputTokens = longValue(tokenUsage, "input_tokens", "inputTokens", "prompt_tokens", "promptTokens");
        long outputTokens = longValue(tokenUsage, "output_tokens", "outputTokens", "completion_tokens", "completionTokens");
        long totalTokens = longValue(tokenUsage, "total_tokens", "totalTokens");
        if (totalTokens <= 0) {
            totalTokens = inputTokens + outputTokens;
        }
        Map<String, Object> normalized = new LinkedHashMap<>();
        normalized.put("inputTokens", inputTokens);
        normalized.put("outputTokens", outputTokens);
        normalized.put("totalTokens", totalTokens);
        return Map.copyOf(normalized);
    }

    private long longValue(Map<String, Object> source, String... keys) {
        for (String key : keys) {
            Object value = source.get(key);
            if (value instanceof Number number) {
                return number.longValue();
            }
        }
        return 0L;
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to serialize responses payload", exception);
        }
    }

    private String sha256(String body) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(body.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 not available", exception);
        }
    }

    PromptPackRegistry.RenderedPrompt renderPrompt(DecisionStageInputV1 input) {
        return promptPackRegistry.renderPrompt(input);
    }

    private String classifyHttpFailure(int statusCode, String body) {
        String normalizedBody = body == null ? "" : body.toLowerCase(java.util.Locale.ROOT);
        if ((statusCode == 400 || statusCode == 422)
                && normalizedBody.contains("effort")) {
            return "provider-rejected-effort";
        }
        if ((statusCode == 400 || statusCode == 404 || statusCode == 422)
                && normalizedBody.contains("model")) {
            return "provider-model-unresolved";
        }
        if (statusCode == 408 || statusCode == 429) {
            return "provider-timeout";
        }
        if (statusCode >= 500) {
            return "provider-http-error";
        }
        return "provider-http-error";
    }

    private boolean retryable(String failureReason) {
        return "provider-timeout".equals(failureReason)
                || "provider-http-error".equals(failureReason)
                || "provider-empty-response".equals(failureReason)
                || "provider-invalid-json".equals(failureReason)
                || "provider-rejected-effort".equals(failureReason);
    }

    private ModelResolution resolveModel(String baseUrl, String apiKey, String configuredModelFamily) {
        ModelResolution cached = cachedModelResolution;
        if (cached != null
                && cached.baseUrl().equals(baseUrl)
                && cached.configuredModelFamily().equals(configuredModelFamily)) {
            return cached;
        }
        synchronized (this) {
            cached = cachedModelResolution;
            if (cached != null
                    && cached.baseUrl().equals(baseUrl)
                    && cached.configuredModelFamily().equals(configuredModelFamily)) {
                return cached;
            }
            TransportResponse response = transport.get(baseUrl, apiKey, properties.getTimeoutMs(), objectMapper, "/models");
            if (response.statusCode() >= 400) {
                throw failure("provider-model-discovery-failed", Map.of(
                        "configuredModelFamily", configuredModelFamily,
                        "providerBaseUrl", baseUrl,
                        "providerWireApi", properties.getWireApi(),
                        "modelDiscoverySource", "/v1/models",
                        "statusCode", response.statusCode()));
            }
            List<ModelCandidate> candidates = parseModelCandidates(response.body(), configuredModelFamily, baseUrl);
            String resolvedModelId = selectResolvedModelId(configuredModelFamily, candidates)
                    .orElseThrow(() -> failure("provider-model-unresolved", Map.of(
                            "configuredModelFamily", configuredModelFamily,
                            "providerBaseUrl", baseUrl,
                            "providerWireApi", properties.getWireApi(),
                            "modelDiscoverySource", "/v1/models",
                            "availableModelIds", candidates.stream().map(ModelCandidate::id).toList())));
            ModelResolution resolved = new ModelResolution(
                    configuredModelFamily,
                    resolvedModelId,
                    baseUrl,
                    "/v1/models",
                    candidates.stream().map(ModelCandidate::id).toList());
            cachedModelResolution = resolved;
            return resolved;
        }
    }

    private List<ModelCandidate> parseModelCandidates(String body,
                                                      String configuredModelFamily,
                                                      String baseUrl) {
        try {
            JsonNode root = objectMapper.readTree(body);
            JsonNode data = root.path("data");
            if (!data.isArray()) {
                throw failure("provider-model-discovery-invalid", Map.of(
                        "configuredModelFamily", configuredModelFamily,
                        "providerBaseUrl", baseUrl,
                        "providerWireApi", properties.getWireApi(),
                        "modelDiscoverySource", "/v1/models"));
            }
            List<ModelCandidate> candidates = new ArrayList<>();
            for (JsonNode modelNode : data) {
                String id = modelNode.path("id").asText("");
                if (id == null || id.isBlank()) {
                    continue;
                }
                String rootValue = modelNode.path("root").asText("");
                candidates.add(new ModelCandidate(id.trim(), rootValue == null ? "" : rootValue.trim()));
            }
            return List.copyOf(candidates);
        } catch (IOException exception) {
            throw failure("provider-model-discovery-invalid", Map.of(
                    "configuredModelFamily", configuredModelFamily,
                    "providerBaseUrl", baseUrl,
                    "providerWireApi", properties.getWireApi(),
                    "modelDiscoverySource", "/v1/models"), exception);
        }
    }

    private Optional<String> selectResolvedModelId(String configuredModelFamily, List<ModelCandidate> candidates) {
        if (configuredModelFamily == null || configuredModelFamily.isBlank() || candidates == null || candidates.isEmpty()) {
            return Optional.empty();
        }
        String normalized = configuredModelFamily.trim();
        if (normalized.contains("/")) {
            return candidates.stream()
                    .map(ModelCandidate::id)
                    .filter(normalized::equals)
                    .findFirst();
        }
        return candidates.stream()
                .filter(candidate -> matchesFamily(candidate, normalized))
                .sorted(Comparator
                        .comparingInt((ModelCandidate candidate) -> prefixPriority(candidate.id()))
                        .thenComparingInt(candidate -> candidate.id().length())
                        .thenComparing(ModelCandidate::id))
                .map(ModelCandidate::id)
                .findFirst();
    }

    private boolean matchesFamily(ModelCandidate candidate, String configuredModelFamily) {
        return configuredModelFamily.equals(candidate.root())
                || configuredModelFamily.equals(candidate.id())
                || candidate.id().endsWith("/" + configuredModelFamily)
                || candidate.root().endsWith("/" + configuredModelFamily);
    }

    private int prefixPriority(String modelId) {
        if (modelId.startsWith("cx/")) {
            return 0;
        }
        if (modelId.startsWith("gh/")) {
            return 1;
        }
        if (modelId.startsWith("cc/")) {
            return 2;
        }
        return 3;
    }

    private String configuredValue(String propertyName, String envName, String defaultValue) {
        String propertyValue = System.getProperty(propertyName);
        if (propertyValue != null && !propertyValue.isBlank()) {
            return propertyValue;
        }
        String envValue = System.getenv(envName);
        if (envValue != null && !envValue.isBlank()) {
            return envValue;
        }
        return defaultValue;
    }

    private NineRouterClientException failure(String failureReason, Map<String, Object> details) {
        return new NineRouterClientException(failureReason, details, null);
    }

    private NineRouterClientException failure(String failureReason, Map<String, Object> details, Throwable cause) {
        return new NineRouterClientException(failureReason, details, cause);
    }

    public record LlmInvocationResult(
            Map<String, Object> parsedOutput,
            String requestedEffort,
            String appliedEffort,
            Map<String, Object> tokenUsage,
            int retryCount,
            String rawResponseHash,
            String rawResponseBody,
            String providerModel,
            String configuredModelFamily,
            String providerBaseUrl,
            String providerWireApi,
            String modelDiscoverySource) {
    }

    public record RuntimeConfiguration(
            String baseUrl,
            String configuredModelFamily,
            String wireApi,
            String provider) {
    }

    record ModelResolution(
            String configuredModelFamily,
            String resolvedModelId,
            String baseUrl,
            String discoverySource,
            List<String> availableModelIds) {
    }

    record ModelCandidate(String id, String root) {
    }

    static final class NineRouterClientException extends IllegalStateException {
        private final String failureReason;
        private final Map<String, Object> details;

        NineRouterClientException(String failureReason, Map<String, Object> details, Throwable cause) {
            super(failureReason, cause);
            this.failureReason = failureReason == null || failureReason.isBlank() ? "provider-http-error" : failureReason;
            this.details = details == null ? Map.of() : Map.copyOf(details);
        }

        String failureReason() {
            return failureReason;
        }

        Map<String, Object> details() {
            return details;
        }
    }

    interface ResponsesTransport {
        TransportResponse get(String baseUrl,
                              String apiKey,
                              Duration timeout,
                              ObjectMapper objectMapper,
                              String relativePath);

        TransportResponse post(String baseUrl,
                               String apiKey,
                               Duration timeout,
                               JsonNode requestBody,
                               ObjectMapper objectMapper);
    }

    static final class DefaultResponsesTransport implements ResponsesTransport {
        private final HttpClient httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        @Override
        public TransportResponse get(String baseUrl,
                                     String apiKey,
                                     Duration timeout,
                                     ObjectMapper objectMapper,
                                     String relativePath) {
            Objects.requireNonNull(baseUrl, "baseUrl");
            try {
                HttpRequest request = HttpRequest.newBuilder(URI.create(trimTrailingSlash(baseUrl) + relativePath))
                        .version(HttpClient.Version.HTTP_1_1)
                        .timeout(timeout)
                        .header("Content-Type", "application/json")
                        .header("Authorization", "Bearer " + apiKey)
                        .header("User-Agent", "IntelligentRouteX/dispatch-v2")
                        .GET()
                        .build();
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                return new TransportResponse(response.statusCode(), response.body());
            } catch (IOException | InterruptedException exception) {
                if (exception instanceof InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new NineRouterClientException("provider-model-discovery-interrupted", Map.of(
                            "providerBaseUrl", baseUrl,
                            "providerWireApi", "models",
                            "exceptionClass", interrupted.getClass().getName(),
                            "exceptionMessage", String.valueOf(interrupted.getMessage())), interrupted);
                }
                throw new NineRouterClientException("provider-model-discovery-failed", Map.of(
                        "providerBaseUrl", baseUrl,
                        "providerWireApi", "models",
                        "exceptionClass", exception.getClass().getName(),
                        "exceptionMessage", String.valueOf(exception.getMessage())), exception);
            }
        }

        @Override
        public TransportResponse post(String baseUrl,
                                      String apiKey,
                                      Duration timeout,
                                      JsonNode requestBody,
                                      ObjectMapper objectMapper) {
            Objects.requireNonNull(baseUrl, "baseUrl");
            try {
                HttpRequest request = HttpRequest.newBuilder(URI.create(trimTrailingSlash(baseUrl) + "/responses"))
                        .version(HttpClient.Version.HTTP_1_1)
                        .timeout(timeout)
                        .header("Content-Type", "application/json")
                        .header("Authorization", "Bearer " + apiKey)
                        .header("User-Agent", "IntelligentRouteX/dispatch-v2")
                        .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(requestBody)))
                        .build();
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                return new TransportResponse(response.statusCode(), response.body());
            } catch (IOException | InterruptedException exception) {
                if (exception instanceof InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new NineRouterClientException("provider-timeout", Map.of(
                            "providerBaseUrl", baseUrl,
                            "providerWireApi", "responses",
                            "exceptionClass", interrupted.getClass().getName(),
                            "exceptionMessage", String.valueOf(interrupted.getMessage())), interrupted);
                }
                throw new NineRouterClientException("provider-http-error", Map.of(
                        "providerBaseUrl", baseUrl,
                        "providerWireApi", "responses",
                        "exceptionClass", exception.getClass().getName(),
                        "exceptionMessage", String.valueOf(exception.getMessage())), exception);
            }
        }

        private String trimTrailingSlash(String value) {
            return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
        }
    }

    record TransportResponse(int statusCode, String body) {
    }
}
