package com.routechain.v2.selector;

import com.google.ortools.Loader;
import com.google.ortools.sat.BoolVar;
import com.google.ortools.sat.CpModel;
import com.google.ortools.sat.CpSolver;
import com.google.ortools.sat.CpSolverStatus;
import com.google.ortools.sat.LinearArgument;
import com.google.ortools.sat.LinearExpr;
import com.routechain.config.RouteChainDispatchV2Properties;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;

public final class OrToolsSetPackingSolver implements SelectorSolver {
    private static final double SCARCE_ORDER_COVERAGE_BONUS = 0.32;
    private static final double SCARCE_COVERAGE_FIRST_BONUS = 2.50;
    private static final AtomicBoolean NATIVE_LIBRARIES_LOADED = new AtomicBoolean(false);
    private static final AtomicBoolean NATIVE_LIBRARIES_UNAVAILABLE = new AtomicBoolean(false);

    private final Duration timeout;
    private final SelectorObjectiveScaler objectiveScaler;

    public OrToolsSetPackingSolver() {
        this(RouteChainDispatchV2Properties.defaults());
    }

    public OrToolsSetPackingSolver(RouteChainDispatchV2Properties properties) {
        this.timeout = properties.getSelector().getOrtools().getTimeout();
        this.objectiveScaler = new SelectorObjectiveScaler(properties.getSelector().getOrtools().getObjectiveScaleFactor());
    }

    @Override
    public SelectorSolverResult solve(List<SelectorCandidate> selectorCandidates, ConflictGraph conflictGraph) {
        try {
            ensureNativeLibrariesLoaded();
        } catch (RuntimeException exception) {
            return new SelectorSolverResult(Optional.empty(), List.of("selector-ortools-unavailable"));
        }

        try {
            return solveModel(selectorCandidates, conflictGraph);
        } catch (RuntimeException exception) {
            return new SelectorSolverResult(Optional.empty(), List.of("selector-ortools-failed"));
        }
    }

    private SelectorSolverResult solveModel(List<SelectorCandidate> selectorCandidates, ConflictGraph conflictGraph) {
        CpModel model = new CpModel();
        List<CandidateDecision> candidateDecisions = new ArrayList<>(selectorCandidates.size());
        Map<String, List<BoolVar>> decisionsByDriver = new HashMap<>();
        Map<String, List<BoolVar>> decisionsByBundle = new HashMap<>();
        Map<String, List<BoolVar>> decisionsByOrder = new HashMap<>();

        for (SelectorCandidate selectorCandidate : selectorCandidates) {
            BoolVar decision = model.newBoolVar("select-" + selectorCandidate.proposalId());
            candidateDecisions.add(new CandidateDecision(selectorCandidate, decision));
            if (!selectorCandidate.feasible()) {
                model.addEquality(decision, 0);
                continue;
            }
            decisionsByDriver.computeIfAbsent(selectorCandidate.driverId(), ignored -> new ArrayList<>()).add(decision);
            decisionsByBundle.computeIfAbsent(selectorCandidate.bundleId(), ignored -> new ArrayList<>()).add(decision);
            for (String orderId : selectorCandidate.orderIds()) {
                decisionsByOrder.computeIfAbsent(orderId, ignored -> new ArrayList<>()).add(decision);
            }
        }

        addAtMostOneConstraints(model, decisionsByDriver);
        addAtMostOneConstraints(model, decisionsByBundle);
        addAtMostOneConstraints(model, decisionsByOrder);

        LinearArgument[] variables = candidateDecisions.stream()
                .map(CandidateDecision::decision)
                .toArray(LinearArgument[]::new);
        boolean scarceBundling = scarceBundling(selectorCandidates);
        long[] coefficients = candidateDecisions.stream()
                .mapToLong(candidateDecision -> objectiveScaler.scale(selectionPriority(candidateDecision.selectorCandidate(), scarceBundling)))
                .toArray();
        model.maximize(LinearExpr.weightedSum(variables, coefficients));

        CpSolver solver = new CpSolver();
        solver.getParameters().setMaxTimeInSeconds(timeout.toMillis() / 1_000.0d);
        solver.getParameters().setNumWorkers(1);
        CpSolverStatus status = solver.solve(model);
        if (status == CpSolverStatus.OPTIMAL) {
            List<SelectorCandidateEnvelope> selectedEnvelopes = candidateDecisions.stream()
                    .filter(candidateDecision -> solver.booleanValue(candidateDecision.decision()))
                    .map(candidateDecision -> new SelectorCandidateEnvelope(candidateDecision.selectorCandidate(), 0.0))
                    .sorted(SelectorCandidateRanking.comparator())
                    .toList();
            List<SelectedProposal> selectedProposals = SelectorCandidateRanking.toSelectedProposals(
                    selectedEnvelopes,
                    ignored -> List.of(scarceBundling ? "selected-by-ortools-scarce-bundling" : "selected-by-ortools"));
            return new SelectorSolverResult(
                    Optional.of(new GlobalSelectionResult(
                            "global-selection-result/v1",
                            selectedProposals,
                            selectorCandidates.size(),
                            selectedProposals.size(),
                            SelectionSolverMode.ORTOOLS,
                            SelectorCandidateRanking.objectiveValue(selectedEnvelopes),
                            scarceBundling ? List.of("scarce-bundling-priority-enabled") : List.of())),
                    List.of());
        }
        if (status == CpSolverStatus.FEASIBLE || status == CpSolverStatus.UNKNOWN) {
            return new SelectorSolverResult(Optional.empty(), List.of("selector-ortools-timeout"));
        }
        return new SelectorSolverResult(Optional.empty(), List.of("selector-ortools-failed"));
    }

    private boolean scarceBundling(List<SelectorCandidate> selectorCandidates) {
        long driverCount = selectorCandidates.stream()
                .filter(SelectorCandidate::feasible)
                .map(SelectorCandidate::driverId)
                .distinct()
                .count();
        long orderCount = selectorCandidates.stream()
                .filter(SelectorCandidate::feasible)
                .flatMap(candidate -> candidate.orderIds().stream())
                .distinct()
                .count();
        boolean hasMultiOrderCandidate = selectorCandidates.stream()
                .filter(SelectorCandidate::feasible)
                .anyMatch(candidate -> candidate.orderIds().size() > 2);
        return driverCount > 0 && hasMultiOrderCandidate && ((double) orderCount / (double) driverCount) >= 2.0;
    }

    private double selectionPriority(SelectorCandidate selectorCandidate, boolean scarceBundling) {
        int orderCount = selectorCandidate.orderIds().size();
        double bundleSizeBonus = scarceBundling ? Math.max(0, orderCount - 2) * SCARCE_ORDER_COVERAGE_BONUS : 0.0;
        double coverageFirstBonus = scarceBundling ? orderCount * SCARCE_COVERAGE_FIRST_BONUS : 0.0;
        return SelectorCandidateRanking.objectiveUtility(selectorCandidate) + coverageFirstBonus + bundleSizeBonus;
    }

    private void addAtMostOneConstraints(CpModel model, Map<String, List<BoolVar>> groupedDecisions) {
        groupedDecisions.values().stream()
                .filter(decisions -> decisions.size() > 1)
                .forEach(decisions -> model.addAtMostOne(decisions.toArray(BoolVar[]::new)));
    }

    private void ensureNativeLibrariesLoaded() {
        if (NATIVE_LIBRARIES_LOADED.get()) {
            return;
        }
        if (NATIVE_LIBRARIES_UNAVAILABLE.get()) {
            throw new IllegalStateException("OR-Tools native libraries unavailable");
        }
        synchronized (NATIVE_LIBRARIES_LOADED) {
            if (NATIVE_LIBRARIES_LOADED.get()) {
                return;
            }
            if (NATIVE_LIBRARIES_UNAVAILABLE.get()) {
                throw new IllegalStateException("OR-Tools native libraries unavailable");
            }
            try {
                Loader.loadNativeLibraries();
                NATIVE_LIBRARIES_LOADED.set(true);
            } catch (RuntimeException | UnsatisfiedLinkError exception) {
                NATIVE_LIBRARIES_UNAVAILABLE.set(true);
                throw new IllegalStateException("OR-Tools native libraries unavailable", exception);
            }
        }
    }

    private record CandidateDecision(
            SelectorCandidate selectorCandidate,
            BoolVar decision) {
    }
}
