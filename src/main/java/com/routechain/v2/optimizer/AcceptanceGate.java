package com.routechain.v2.optimizer;

import com.routechain.v2.constraints.FeasibilityOracle;
import com.routechain.v2.objective.ObjectiveBreakdown;
import com.routechain.v2.objective.ObjectiveConfig;
import com.routechain.v2.objective.UnifiedObjective;
import com.routechain.v2.selector.SelectorCandidate;

public final class AcceptanceGate {
    private final FeasibilityOracle feasibilityOracle;
    private final UnifiedObjective objective;
    private final ObjectiveConfig config;

    public AcceptanceGate() {
        this(new FeasibilityOracle(), new UnifiedObjective(), ObjectiveConfig.defaults());
    }

    public AcceptanceGate(FeasibilityOracle feasibilityOracle,
                          UnifiedObjective objective,
                          ObjectiveConfig config) {
        this.feasibilityOracle = feasibilityOracle;
        this.objective = objective;
        this.config = config;
    }

    public boolean canReplace(SelectorCandidate incumbent, SelectorCandidate challenger) {
        if (!feasibilityOracle.check(challenger).feasible()) {
            return false;
        }
        if (incumbent == null || !feasibilityOracle.check(incumbent).feasible()) {
            return true;
        }
        ObjectiveBreakdown incumbentBreakdown = objective.scoreSelectorCandidate(incumbent);
        ObjectiveBreakdown challengerBreakdown = objective.scoreSelectorCandidate(challenger);
        double requiredDelta = Math.abs(incumbentBreakdown.totalScore()) * (config.scoreEpsilonPct() / 100.0);
        return challengerBreakdown.totalScore() > incumbentBreakdown.totalScore() + requiredDelta;
    }
}
