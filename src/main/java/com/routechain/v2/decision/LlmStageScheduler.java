package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

public final class LlmStageScheduler {
    private final NineRouterResponsesClient client;
    private final DecisionEffortPolicy effortPolicy;
    private final RouteChainDispatchV2Properties.Decision decisionProperties;
    private final DecisionStageLogger decisionStageLogger;
    private final ComparisonPackBuilder comparisonPackBuilder;
    private final DecisionSessionStore sessionStore;

    public LlmStageScheduler(NineRouterResponsesClient client,
                             RouteChainDispatchV2Properties.Decision decisionProperties,
                             DecisionStageLogger decisionStageLogger,
                             DecisionSessionStore sessionStore) {
        this.client = client;
        this.decisionProperties = decisionProperties;
        this.decisionStageLogger = decisionStageLogger;
        this.sessionStore = sessionStore;
        this.effortPolicy = new DecisionEffortPolicy(decisionProperties);
        this.comparisonPackBuilder = new ComparisonPackBuilder();
    }

    public NineRouterResponsesClient.RuntimeConfiguration runtimeConfiguration() {
        return client.runtimeConfiguration();
    }

    PromptPackRegistry.RenderedPrompt renderPrompt(DecisionStageInputV1 input) {
        return client.renderPrompt(input);
    }

    public DecisionStageOutputV1 evaluate(DecisionStageInputV1 input) {
        long startedAt = System.nanoTime();
        DecisionSessionStore.SessionStartResult sessionStart = sessionStore.beginSession(input);
        if (!sessionStart.manifest().isEmpty()) {
            decisionStageLogger.writeFamily("decision_session_manifest", input.traceId(), input.stageName().wireName(), sessionStart.manifest());
        }
        DecisionSessionStore.SessionContext sessionContext = sessionStore.resolveContext(input);
        decisionStageLogger.writeFamily("decision_session_ref_trace", input.traceId(), input.stageName().wireName(), Map.of(
                "schemaVersion", "decision-session-ref-trace/v1",
                "traceId", input.traceId(),
                "stageName", input.stageName().wireName(),
                "promptFamily", decisionProperties.getLlm().getPromptFamily(),
                "sessionStoreEnabled", sessionStore.sessionStoreEnabled(),
                "sessionNamespace", sessionContext.sessionNamespace(),
                "sessionRefCount", sessionContext.sessionRefCount(),
                "sessionReadRefs", sessionContext.sessionReadRefs(),
                "sessionRefs", sessionContext.sessionRefs()));
        DecisionEffortPolicy.EffortDecision effortDecision = effortPolicy.select(input);
        List<PassTrace> passTraces = multiPassEnabled(input.stageName()) ? runMultiPass(input, effortDecision) : runSinglePass(input, effortDecision);
        PassTrace commitTrace = passTraces.getLast();
        decisionStageLogger.writeFamily("llm_reasoning_cycle_trace", input.traceId(), input.stageName().wireName(), Map.of(
                "schemaVersion", "llm-reasoning-cycle-trace/v1",
                "traceId", input.traceId(),
                "stageName", input.stageName().wireName(),
                "requestedEffort", effortDecision.requestedEffort().wireValue(),
                "selectionReason", effortDecision.selectionReason(),
                "passes", passTraces.stream().map(PassTrace::toMap).toList()));
        NineRouterResponsesClient.LlmInvocationResult representative = commitTrace.result();
        DecisionStageOutputV1 output = new DecisionStageOutputV1(
                "stage-output-v1",
                input.traceId(),
                input.runId(),
                input.tickId(),
                input.stageName(),
                DecisionBrainType.LLM,
                representative.providerModel(),
                extractAssessments(representative.parsedOutput()),
                extractSelectedIds(representative.parsedOutput()),
                new DecisionStageMetaV1(
                        "decision-stage-meta/v1",
                        elapsedMs(startedAt),
                        confidence(representative.parsedOutput()),
                        false,
                        null,
                        true,
                        "llm",
                        effortDecision.requestedEffort().wireValue(),
                        representative.appliedEffort(),
                        mergeTokenUsage(passTraces),
                        passTraces.stream().mapToInt(trace -> trace.result().retryCount()).sum(),
                        representative.rawResponseHash(),
                        "llm",
                        authoritativeStages(input),
                        mergeQualityFlags(input, effortDecision, passTraces, representative),
                        String.valueOf(input.contextSelection().getOrDefault("profileName", "balanced")),
                        overlays(input),
                        Boolean.TRUE.equals(input.contextSelection().get("compressed")),
                        effortDecision.selectionReason()));
        DecisionSessionStore.StageSessionRecord stageSessionRecord = sessionStore.recordStageResult(
                input,
                output,
                passTraces.stream().map(PassTrace::summary).toList());
        if (!stageSessionRecord.stageSummary().isEmpty()) {
            decisionStageLogger.writeFamily("decision_session_stage_summary", input.traceId(), input.stageName().wireName(), stageSessionRecord.stageSummary());
        }
        return output;
    }

    private List<PassTrace> runSinglePass(DecisionStageInputV1 input,
                                          DecisionEffortPolicy.EffortDecision effortDecision) {
        DecisionStageInputV1 commitInput = passInput(input, "commit", "single-pass final commit");
        PromptPackRegistry.RenderedPrompt renderedPrompt = client.renderPrompt(commitInput);
        logPromptSpec(commitInput, "commit", renderedPrompt);
        NineRouterResponsesClient.LlmInvocationResult result = client.invoke(commitInput, effortDecision.requestedEffort(), renderedPrompt);
        recordPass(commitInput, "commit", renderedPrompt, result);
        return List.of(new PassTrace("commit", "single-pass final commit", result));
    }

    private List<PassTrace> runMultiPass(DecisionStageInputV1 input,
                                         DecisionEffortPolicy.EffortDecision effortDecision) {
        List<PassTrace> traces = new ArrayList<>();
        DecisionStageInputV1 proposeInput = passInput(input, "propose", "produce a shortlist and provisional ranking");
        PromptPackRegistry.RenderedPrompt proposePrompt = client.renderPrompt(proposeInput);
        logPromptSpec(proposeInput, "propose", proposePrompt);
        NineRouterResponsesClient.LlmInvocationResult propose = client.invoke(
                proposeInput,
                effortDecision.requestedEffort(),
                proposePrompt);
        recordPass(proposeInput, "propose", proposePrompt, propose);
        traces.add(new PassTrace("propose", "produce a shortlist and provisional ranking", propose));

        DecisionStageInputV1 critiqueInput = passInput(input.withUpstreamSummary(withPassSummary(input.upstreamSummary(), traces)),
                "critique",
                "identify dominated candidates, missing trade-offs, regret, and conflict risk");
        PromptPackRegistry.RenderedPrompt critiquePrompt = client.renderPrompt(critiqueInput);
        logPromptSpec(critiqueInput, "critique", critiquePrompt);
        NineRouterResponsesClient.LlmInvocationResult critique = client.invoke(
                critiqueInput,
                effortDecision.requestedEffort(),
                critiquePrompt);
        recordPass(critiqueInput, "critique", critiquePrompt, critique);
        traces.add(new PassTrace("critique", "identify dominated candidates, missing trade-offs, regret, and conflict risk", critique));

        DecisionStageInputV1 compareInput = input
                .withComparisonPack(comparisonPackBuilder.augmentForPasses(input.comparisonPack(), propose.parsedOutput(), critique.parsedOutput()))
                .withUpstreamSummary(withPassSummary(input.upstreamSummary(), traces));
        DecisionStageInputV1 comparePassInput = passInput(compareInput, "compare", "re-rank candidates using critique feedback and relative deltas");
        PromptPackRegistry.RenderedPrompt comparePrompt = client.renderPrompt(comparePassInput);
        logPromptSpec(comparePassInput, "compare", comparePrompt);
        NineRouterResponsesClient.LlmInvocationResult compare = client.invoke(
                comparePassInput,
                effortDecision.requestedEffort(),
                comparePrompt);
        recordPass(comparePassInput, "compare", comparePrompt, compare);
        traces.add(new PassTrace("compare", "re-rank candidates using critique feedback and relative deltas", compare));

        DecisionStageInputV1 commitInput = input
                .withComparisonPack(comparisonPackBuilder.augmentForPasses(input.comparisonPack(), compare.parsedOutput(), critique.parsedOutput()))
                .withUpstreamSummary(withPassSummary(input.upstreamSummary(), traces));
        DecisionStageInputV1 commitPassInput = passInput(commitInput, "commit", "return the final authoritative stage_output_v1 decision");
        PromptPackRegistry.RenderedPrompt commitPrompt = client.renderPrompt(commitPassInput);
        logPromptSpec(commitPassInput, "commit", commitPrompt);
        NineRouterResponsesClient.LlmInvocationResult commit = client.invoke(
                commitPassInput,
                effortDecision.requestedEffort(),
                commitPrompt);
        recordPass(commitPassInput, "commit", commitPrompt, commit);
        traces.add(new PassTrace("commit", "return the final authoritative stage_output_v1 decision", commit));
        return List.copyOf(traces);
    }

    private void logPromptSpec(DecisionStageInputV1 input,
                               String passType,
                               PromptPackRegistry.RenderedPrompt renderedPrompt) {
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>(renderedPrompt.metadata());
        payload.put("schemaVersion", "llm-prompt-spec-trace/v1");
        payload.put("traceId", input.traceId());
        payload.put("stageName", input.stageName().wireName());
        payload.put("passType", passType);
        decisionStageLogger.writeFamily("llm_prompt_spec_trace", input.traceId(), input.stageName().wireName() + "-" + passType, Map.copyOf(payload));
    }

    private void recordPass(DecisionStageInputV1 input,
                            String passType,
                            PromptPackRegistry.RenderedPrompt renderedPrompt,
                            NineRouterResponsesClient.LlmInvocationResult result) {
        sessionStore.recordPass(input, passType, renderedPrompt, result);
        LinkedHashMap<String, Object> payload = new LinkedHashMap<>();
        payload.put("schemaVersion", "llm-skill-activation-trace/v1");
        payload.put("traceId", input.traceId());
        payload.put("stageName", input.stageName().wireName());
        payload.put("passType", passType);
        payload.put("skillSetVersion", renderedPrompt.metadata().getOrDefault("skillSetVersion", ""));
        payload.put("skillIdsActivated", renderedPrompt.metadata().getOrDefault("skillIdsActivated", List.of()));
        payload.put("sessionStoreEnabled", renderedPrompt.metadata().getOrDefault("sessionStoreEnabled", false));
        payload.put("sessionNamespace", renderedPrompt.metadata().getOrDefault("sessionNamespace", ""));
        payload.put("sessionReadRefs", renderedPrompt.metadata().getOrDefault("sessionReadRefs", List.of()));
        payload.put("sessionWriteRefs", renderedPrompt.metadata().getOrDefault("sessionWriteRefs", List.of()));
        payload.put("sessionRefCount", renderedPrompt.metadata().getOrDefault("sessionRefCount", 0));
        payload.put("promptFamily", renderedPrompt.metadata().getOrDefault("promptFamily", "v2"));
        decisionStageLogger.writeFamily("llm_skill_activation_trace", input.traceId(), input.stageName().wireName() + "-" + passType, Map.copyOf(payload));
    }

    private DecisionStageInputV1 passInput(DecisionStageInputV1 input, String passType, String passObjective) {
        LinkedHashMap<String, Object> contextSelection = new LinkedHashMap<>(input.contextSelection());
        contextSelection.put("passType", passType);
        contextSelection.put("passObjective", passObjective);
        return input.withContextSelection(Map.copyOf(contextSelection));
    }

    private Map<String, Object> withPassSummary(Map<String, Object> upstreamSummary, List<PassTrace> passTraces) {
        LinkedHashMap<String, Object> merged = new LinkedHashMap<>(upstreamSummary == null ? Map.of() : upstreamSummary);
        merged.put("llmPasses", passTraces.stream().map(PassTrace::summary).toList());
        return Map.copyOf(merged);
    }

    private boolean multiPassEnabled(DecisionStageName stageName) {
        return decisionProperties.getLlm().isMultiPassEnabled()
                && decisionProperties.getLlm().getMultiPassStages().stream().anyMatch(stageName.wireName()::equals);
    }

    private List<String> extractSelectedIds(Map<String, Object> parsedOutput) {
        Object selectedIds = parsedOutput.get("selectedIds");
        if (selectedIds instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        return List.of();
    }

    private Map<String, Object> extractAssessments(Map<String, Object> parsedOutput) {
        Object assessments = parsedOutput.get("assessments");
        if (assessments instanceof Map<?, ?> map) {
            LinkedHashMap<String, Object> converted = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                converted.put(String.valueOf(entry.getKey()), entry.getValue());
            }
            return Map.copyOf(converted);
        }
        return Map.of();
    }

    private double confidence(Map<String, Object> parsedOutput) {
        Object assessments = parsedOutput.get("assessments");
        if (!(assessments instanceof Map<?, ?> assessmentMap)) {
            return 0.75;
        }
        Object items = assessmentMap.get("items");
        if (!(items instanceof List<?> itemList) || itemList.isEmpty()) {
            return 0.75;
        }
        return itemList.stream()
                .filter(Map.class::isInstance)
                .map(Map.class::cast)
                .mapToDouble(item -> {
                    Object value = item.get("confidence");
                    return value instanceof Number number ? number.doubleValue() : 0.0;
                })
                .average()
                .orElse(0.75);
    }

    private Map<String, Object> mergeTokenUsage(List<PassTrace> passTraces) {
        long inputTokens = 0L;
        long outputTokens = 0L;
        long totalTokens = 0L;
        for (PassTrace passTrace : passTraces) {
            inputTokens += longValue(passTrace.result().tokenUsage(), "inputTokens");
            outputTokens += longValue(passTrace.result().tokenUsage(), "outputTokens");
            totalTokens += longValue(passTrace.result().tokenUsage(), "totalTokens");
        }
        return Map.of(
                "inputTokens", inputTokens,
                "outputTokens", outputTokens,
                "totalTokens", totalTokens,
                "requestCount", passTraces.size());
    }

    private long longValue(Map<String, Object> source, String key) {
        Object value = source.get(key);
        return value instanceof Number number ? number.longValue() : 0L;
    }

    private long elapsedMs(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000L;
    }

    private List<String> overlays(DecisionStageInputV1 input) {
        Object overlays = input.contextSelection().get("overlays");
        if (overlays instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        return List.of();
    }

    private List<String> authoritativeStages(DecisionStageInputV1 input) {
        Object raw = input.dispatchContext().get("authoritativeStages");
        if (raw instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        return List.of();
    }

    private List<String> mergeQualityFlags(DecisionStageInputV1 input,
                                           DecisionEffortPolicy.EffortDecision effortDecision,
                                           List<PassTrace> passTraces,
                                           NineRouterResponsesClient.LlmInvocationResult representative) {
        LinkedHashSet<String> flags = new LinkedHashSet<>();
        Object selectionFlags = input.contextSelection().get("qualityFlags");
        if (selectionFlags instanceof List<?> list) {
            list.stream().map(String::valueOf).forEach(flags::add);
        }
        flags.addAll(effortDecision.qualityFlags());
        flags.add(multiPassEnabled(input.stageName()) ? "multi-pass-active" : "single-pass-active");
        flags.add("llm-pass-count-" + passTraces.size());
        if (!representative.requestedEffort().equals(representative.appliedEffort())) {
            flags.add("effort-downgraded");
        }
        return List.copyOf(flags);
    }

    private record PassTrace(
            String passType,
            String passObjective,
            NineRouterResponsesClient.LlmInvocationResult result) {
        Map<String, Object> toMap() {
            return Map.of(
                    "passType", passType,
                    "passObjective", passObjective,
                    "requestedEffort", result.requestedEffort(),
                    "appliedEffort", result.appliedEffort(),
                    "retryCount", result.retryCount(),
                    "selectedIds", result.parsedOutput().getOrDefault("selectedIds", List.of()),
                    "rawResponseHash", result.rawResponseHash());
        }

        Map<String, Object> summary() {
            return Map.of(
                    "passType", passType,
                    "selectedIds", result.parsedOutput().getOrDefault("selectedIds", List.of()),
                    "assessments", result.parsedOutput().getOrDefault("assessments", Map.of()));
        }
    }
}
