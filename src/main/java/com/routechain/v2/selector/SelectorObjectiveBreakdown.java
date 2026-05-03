package com.routechain.v2.selector;

import com.routechain.v2.objective.ObjectiveBreakdown;

public record SelectorObjectiveBreakdown(
        String proposalId,
        ObjectiveBreakdown objectiveBreakdown) {
}
