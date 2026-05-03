package com.routechain.v2.selector;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.util.ArrayList;
import java.util.List;

public final class GlobalSelector {
    private final RouteChainDispatchV2Properties properties;
    private final GreedyRepairSelector greedyRepairSelector;
    private final SelectorSolver selectorSolver;
    private final MiniExactSelector miniExactSelector;
    private final FastIncumbentBuilder fastIncumbentBuilder;
    private final SelectorPoolReducer selectorPoolReducer;
    private final AcceptanceGate acceptanceGate;

    public GlobalSelector(RouteChainDispatchV2Properties properties,
                          GreedyRepairSelector greedyRepairSelector,
                          SelectorSolver selectorSolver) {
        this.properties = properties;
        this.greedyRepairSelector = greedyRepairSelector;
        this.selectorSolver = selectorSolver;
        this.miniExactSelector = new MiniExactSelector();
        this.fastIncumbentBuilder = new FastIncumbentBuilder();
        this.selectorPoolReducer = new SelectorPoolReducer();
        this.acceptanceGate = new AcceptanceGate();
    }

    public SelectorSelectionOutcome select(List<SelectorCandidateEnvelope> candidateEnvelopes,
                                           ConflictGraph conflictGraph) {
        SelectorPoolReductionResult poolReduction = selectorPoolReducer.reduce(
                candidateEnvelopes,
                properties.getSelector().getMaxPoolSize());
        List<SelectorCandidateEnvelope> reducedCandidateEnvelopes = poolReduction.retainedCandidates();
        java.util.Optional<SelectorCandidateEnvelope> fastIncumbent = fastIncumbentBuilder.build(reducedCandidateEnvelopes);
        if (reducedCandidateEnvelopes.isEmpty()) {
            return fastIncumbent
                    .map(incumbent -> incumbentOnly(candidateEnvelopes.size(), incumbent, appendDistinct(
                            poolReduction.reasons(),
                            "selector-returned-fast-incumbent-no-reduced-pool")))
                    .orElseGet(() -> withPoolReductionReasons(
                            greedyRepairSelector.select(reducedCandidateEnvelopes, reducedConflictGraph(List.of()), SelectionSolverMode.DEGRADED_GREEDY, false),
                            candidateEnvelopes.size(),
                            poolReduction));
        }
        ConflictGraph reducedConflictGraph = reducedConflictGraph(reducedCandidateEnvelopes);
        boolean repairEnabled = properties.getSelector().isGreedyRepairEnabled()
                && properties.getSelector().getRepairPassLimit() > 0;
        if (!properties.getSelector().isGlobalSelectorEnabled()) {
            SelectorSelectionOutcome outcome = greedyRepairSelector.select(
                    reducedCandidateEnvelopes,
                    reducedConflictGraph,
                    SelectionSolverMode.DEGRADED_GREEDY,
                    false);
            return withAcceptanceAndPoolTelemetry(outcome, null, candidateEnvelopes.size(), poolReduction, false, "GLOBAL_SELECTOR_DISABLED");
        }
        if (miniExactSelector.shouldUse(reducedCandidateEnvelopes)) {
            SelectorSelectionOutcome outcome = miniExactSelector.select(reducedCandidateEnvelopes, reducedConflictGraph);
            return withAcceptanceAndPoolTelemetry(outcome, null, candidateEnvelopes.size(), poolReduction, false, "NONE");
        }
        if (!properties.isSelectorOrtoolsEnabled()) {
            SelectorSelectionOutcome outcome = greedyRepairSelector.select(
                    reducedCandidateEnvelopes,
                    reducedConflictGraph,
                    SelectionSolverMode.GREEDY_REPAIR,
                    repairEnabled);
            return withAcceptanceAndPoolTelemetry(outcome, null, candidateEnvelopes.size(), poolReduction, false, "NONE");
        }

        SelectorSelectionOutcome greedyIncumbent = greedyRepairSelector.select(
                reducedCandidateEnvelopes,
                reducedConflictGraph,
                SelectionSolverMode.GREEDY_REPAIR,
                repairEnabled);

        SelectorSolverResult solverResult = selectorSolver.solve(
                reducedCandidateEnvelopes.stream().map(SelectorCandidateEnvelope::candidate).toList(),
                reducedConflictGraph);
        if (solverResult.selectionResult().isPresent()) {
            GlobalSelectionResult solverSelection = solverResult.selectionResult().get();
            if (solverSelection.objectiveValue() + 1e-9 < greedyIncumbent.selectionResult().objectiveValue()) {
                return new SelectorSelectionOutcome(
                        withSelectionTelemetry(withDegradeReasons(greedyIncumbent.selectionResult(), appendDistinct(
                                appendAll(solverResult.degradeReasons(), poolReduction.reasons()),
                                "selector-solver-objective-below-greedy")),
                                candidateEnvelopes.size(),
                                poolReduction,
                                false,
                                "GREEDY_INCUMBENT",
                                acceptanceGate.evaluate(null, greedyIncumbent.selectionResult(), reducedCandidateEnvelopes)),
                        greedyIncumbent.decisionTrace());
            }
            SelectorSelectionOutcome solverOutcome = new SelectorSelectionOutcome(
                    withDegradeReasons(solverSelection, solverResult.degradeReasons()),
                    SelectorDecisionTrace.empty());
            return withAcceptanceAndPoolTelemetry(solverOutcome, greedyIncumbent.selectionResult(), candidateEnvelopes.size(), poolReduction, false, "NONE");
        }

        boolean timeout = solverResult.degradeReasons().stream().anyMatch(reason -> reason.contains("timeout"));
        SelectionSolverMode fallbackMode = timeout ? SelectionSolverMode.CP_SAT_TIMEOUT_INCUMBENT : SelectionSolverMode.DEGRADED_GREEDY;
        SelectorSelectionOutcome degradedOutcome = timeout
                ? new SelectorSelectionOutcome(
                new GlobalSelectionResult(
                        greedyIncumbent.selectionResult().schemaVersion(),
                        greedyIncumbent.selectionResult().selectedProposals(),
                        greedyIncumbent.selectionResult().retainedCandidateCount(),
                        greedyIncumbent.selectionResult().selectedCount(),
                        fallbackMode,
                        greedyIncumbent.selectionResult().objectiveValue(),
                        appendDistinct(greedyIncumbent.selectionResult().degradeReasons(), "selector-returned-greedy-incumbent-after-timeout")),
                greedyIncumbent.decisionTrace())
                : greedyRepairSelector.select(
                reducedCandidateEnvelopes,
                reducedConflictGraph,
                fallbackMode,
                repairEnabled);
        return new SelectorSelectionOutcome(
                withSelectionTelemetry(
                        withDegradeReasons(degradedOutcome.selectionResult(), solverResult.degradeReasons()),
                        candidateEnvelopes.size(),
                        poolReduction,
                        timeout,
                        timeout ? "CP_SAT_TIMEOUT_INCUMBENT" : "DEGRADED_GREEDY",
                        acceptanceGate.evaluate(null, degradedOutcome.selectionResult(), reducedCandidateEnvelopes)),
                degradedOutcome.decisionTrace());
    }

    private ConflictGraph reducedConflictGraph(List<SelectorCandidateEnvelope> reducedCandidateEnvelopes) {
        return new ConflictGraphBuilder().build(reducedCandidateEnvelopes.stream()
                .map(SelectorCandidateEnvelope::candidate)
                .toList());
    }

    private SelectorSelectionOutcome incumbentOnly(int retainedCandidateCount,
                                                   SelectorCandidateEnvelope incumbent,
                                                   List<String> degradeReasons) {
        List<SelectedProposal> selectedProposals = SelectorCandidateRanking.toSelectedProposals(
                List.of(incumbent),
                ignored -> List.of("selected-by-fast-incumbent"));
        return new SelectorSelectionOutcome(
                new GlobalSelectionResult(
                        "global-selection-result/v1",
                        selectedProposals,
                        retainedCandidateCount,
                        selectedProposals.size(),
                        SelectionSolverMode.DEGRADED_GREEDY,
                        SelectorCandidateRanking.objectiveValue(List.of(incumbent)),
                        degradeReasons),
                SelectorDecisionTrace.empty());
    }

    private SelectorSelectionOutcome withPoolReductionReasons(SelectorSelectionOutcome outcome,
                                                             int originalCandidateCount,
                                                             SelectorPoolReductionResult poolReduction) {
        List<String> reasons = new ArrayList<>(poolReduction.reasons());
        if (poolReduction.rejectedCandidateCount() > 0) {
            reasons.add("selector-pool-rejected-candidates-" + poolReduction.rejectedCandidateCount());
        }
        poolReduction.violationCountsByCode().keySet().stream()
                .map(code -> "selector-feasibility-violation-" + code)
                .forEach(reasons::add);
        return new SelectorSelectionOutcome(
                new GlobalSelectionResult(
                        outcome.selectionResult().schemaVersion(),
                        outcome.selectionResult().selectedProposals(),
                        originalCandidateCount,
                        outcome.selectionResult().selectedCount(),
                        outcome.selectionResult().solverMode(),
                        outcome.selectionResult().objectiveValue(),
                        appendAll(outcome.selectionResult().degradeReasons(), reasons)),
                outcome.decisionTrace());
    }

    private SelectorSelectionOutcome withAcceptanceAndPoolTelemetry(SelectorSelectionOutcome outcome,
                                                                    GlobalSelectionResult incumbent,
                                                                    int originalCandidateCount,
                                                                    SelectorPoolReductionResult poolReduction,
                                                                    boolean selectorTimedOut,
                                                                    String fallbackLevel) {
        AcceptanceGateResult gateResult = acceptanceGate.evaluate(incumbent, outcome.selectionResult(), poolReduction.retainedCandidates());
        GlobalSelectionResult candidateResult = withSelectionTelemetry(
                outcome.selectionResult(),
                originalCandidateCount,
                poolReduction,
                selectorTimedOut,
                fallbackLevel,
                gateResult);
        if (gateResult.accepted()) {
            return new SelectorSelectionOutcome(candidateResult, outcome.decisionTrace());
        }
        GlobalSelectionResult fallbackResult = incumbent == null
                ? candidateResult
                : withSelectionTelemetry(
                withDegradeReasons(incumbent, appendAll(gateResult.rejectedReasons(), List.of("selector-acceptance-gate-rejected-candidate"))),
                originalCandidateCount,
                poolReduction,
                selectorTimedOut,
                "ACCEPTANCE_GATE_INCUMBENT",
                gateResult);
        return new SelectorSelectionOutcome(fallbackResult, outcome.decisionTrace());
    }

    private GlobalSelectionResult withSelectionTelemetry(GlobalSelectionResult selectionResult,
                                                        int originalCandidateCount,
                                                        SelectorPoolReductionResult poolReduction,
                                                        boolean selectorTimedOut,
                                                        String fallbackLevel,
                                                        AcceptanceGateResult gateResult) {
        List<String> poolReasons = new ArrayList<>(poolReduction.reasons());
        if (poolReduction.rejectedCandidateCount() > 0) {
            poolReasons.add("selector-pool-rejected-candidates-" + poolReduction.rejectedCandidateCount());
        }
        poolReduction.violationCountsByCode().keySet().stream()
                .map(code -> "selector-feasibility-violation-" + code)
                .forEach(poolReasons::add);
        List<String> acceptanceReasons = gateResult == null ? List.of() : gateResult.rejectedReasons();
        return new GlobalSelectionResult(
                selectionResult.schemaVersion(),
                selectionResult.selectedProposals(),
                originalCandidateCount,
                selectionResult.selectedCount(),
                selectionResult.solverMode(),
                selectionResult.objectiveValue(),
                originalCandidateCount,
                poolReduction.retainedCandidates().size(),
                poolReduction.feasibleCandidateCount(),
                poolReduction.rejectedCandidateCount(),
                selectorTimedOut,
                fallbackLevel == null || fallbackLevel.isBlank() ? "NONE" : fallbackLevel,
                gateResult == null || gateResult.accepted(),
                acceptanceReasons,
                poolReduction.maxPoolSize(),
                poolReduction.poolCapApplied(),
                poolReduction.retainedBestObjectiveUtility(),
                poolReduction.feasibleBestObjectiveUtility(),
                appendAll(appendAll(selectionResult.degradeReasons(), poolReasons), acceptanceReasons));
    }

    private List<String> appendDistinct(List<String> reasons, String reason) {
        List<String> appended = new ArrayList<>(reasons);
        appended.add(reason);
        return appended.stream().distinct().toList();
    }

    private List<String> appendAll(List<String> reasons, List<String> extraReasons) {
        List<String> appended = new ArrayList<>(reasons);
        appended.addAll(extraReasons);
        return appended.stream().distinct().toList();
    }

    private GlobalSelectionResult withDegradeReasons(GlobalSelectionResult selectionResult, List<String> extraDegradeReasons) {
        List<String> degradeReasons = new ArrayList<>(selectionResult.degradeReasons());
        degradeReasons.addAll(extraDegradeReasons);
        return new GlobalSelectionResult(
                selectionResult.schemaVersion(),
                selectionResult.selectedProposals(),
                selectionResult.retainedCandidateCount(),
                selectionResult.selectedCount(),
                selectionResult.solverMode(),
                selectionResult.objectiveValue(),
                degradeReasons.stream().distinct().toList());
    }
}
