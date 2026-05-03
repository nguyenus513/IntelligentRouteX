package com.routechain.v2.selector;

import com.routechain.v2.constraints.FeasibilityOracle;

import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public final class FastIncumbentBuilder {
    private static final Duration DEFAULT_BUDGET = Duration.ofMillis(50);
    private final FeasibilityOracle feasibilityOracle;

    public FastIncumbentBuilder() {
        this(new FeasibilityOracle());
    }

    public FastIncumbentBuilder(FeasibilityOracle feasibilityOracle) {
        this.feasibilityOracle = feasibilityOracle;
    }

    public Optional<SelectorCandidateEnvelope> build(List<SelectorCandidateEnvelope> candidateEnvelopes) {
        long deadline = System.nanoTime() + DEFAULT_BUDGET.toNanos();
        return candidateEnvelopes.stream()
                .filter(envelope -> System.nanoTime() <= deadline)
                .filter(envelope -> feasibilityOracle.check(envelope.candidate()).feasible())
                .max(Comparator
                        .comparingDouble((SelectorCandidateEnvelope envelope) -> envelope.candidate().selectionScore())
                        .thenComparing(envelope -> envelope.candidate().orderIds().size())
                        .thenComparing(envelope -> envelope.candidate().proposalId(), Comparator.reverseOrder()));
    }
}
