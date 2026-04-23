package com.routechain.v2.decision;

import java.util.List;
import java.util.Map;

record PromptSpecManifest(
        String promptSpecVersion,
        String packetTemplateVersion,
        String skillSetVersion,
        List<String> requiredGlobalPacks,
        Map<String, StagePromptResourceEntry> stageMappings) {

    record StagePromptResourceEntry(
            String systemPrompt,
            String packetTemplate,
            String skillSet) {
    }
}
