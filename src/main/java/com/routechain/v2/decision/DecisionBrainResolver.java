package com.routechain.v2.decision;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.EnumSet;

public final class DecisionBrainResolver {
    private final RouteChainDispatchV2Properties properties;
    private final LegacyMlBrain legacyMlBrain;
    private final LlmBrain llmBrain;
    private final StudentBrain studentBrain;

    public DecisionBrainResolver(RouteChainDispatchV2Properties properties,
                                 LegacyMlBrain legacyMlBrain,
                                 LlmBrain llmBrain,
                                 StudentBrain studentBrain) {
        this.properties = properties;
        this.legacyMlBrain = legacyMlBrain;
        this.llmBrain = llmBrain;
        this.studentBrain = studentBrain;
    }

    public ResolvedDecisionBrain resolve() {
        DecisionRuntimeMode runtimeMode = DecisionRuntimeMode.fromMode(properties.getDecision().getMode());
        DecisionBrainType requestedType = DecisionBrainType.fromMode(properties.getDecision().getMode());
        return switch (requestedType) {
            case LEGACY -> new ResolvedDecisionBrain(
                    requestedType,
                    DecisionBrainType.LEGACY,
                    legacyMlBrain,
                    legacyMlBrain,
                    false,
                    null,
                    runtimeMode,
                    EnumSet.noneOf(DecisionStageName.class));
            case STUDENT -> new ResolvedDecisionBrain(
                    requestedType,
                    DecisionBrainType.STUDENT,
                    studentBrain,
                    legacyMlBrain,
                    false,
                    null,
                    runtimeMode,
                    EnumSet.noneOf(DecisionStageName.class));
            case LLM -> resolveLlm(requestedType, runtimeMode);
        };
    }

    private ResolvedDecisionBrain resolveLlm(DecisionBrainType requestedType, DecisionRuntimeMode runtimeMode) {
        return new ResolvedDecisionBrain(
                requestedType,
                DecisionBrainType.LEGACY,
                legacyMlBrain,
                legacyMlBrain,
                true,
                "llm-disabled-by-policy",
                runtimeMode,
                EnumSet.noneOf(DecisionStageName.class));
    }
}
