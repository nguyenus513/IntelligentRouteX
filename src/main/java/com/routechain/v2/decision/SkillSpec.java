package com.routechain.v2.decision;

import java.util.List;

record SkillSpec(
        String skillId,
        String description,
        List<String> requiredInputs,
        List<String> forbiddenAssumptions,
        List<String> outputEmphasis,
        List<String> recommendedReasonCodes,
        List<String> allowedToolIds) {
}
