package com.routechain.v2.route;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.EtaContext;

import java.util.ArrayList;
import java.util.List;

public final class RouteProposalBudgetPolicy {
    private final RouteChainDispatchV2Properties properties;

    public RouteProposalBudgetPolicy(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public RouteProposalBudgetDecision decide(DispatchV2Request request,
                                              EtaContext etaContext,
                                              int bundleCount,
                                              int driverCandidateCount,
                                              double previousGeometryCoverage) {
        RouteChainDispatchV2Properties.Candidate.RouteProposalBudget budget = properties.getCandidate().getRouteProposalBudget();
        int defaultTotal = Math.max(1, driverCandidateCount * 3);
        if (!budget.isEnabled()) {
            return new RouteProposalBudgetDecision(
                    false,
                    "disabled",
                    defaultTotal,
                    Math.max(1, properties.getCandidate().getMaxDrivers()),
                    Math.max(1, properties.getCandidate().getMaxAnchors()),
                    Math.max(1, properties.getCandidate().getMaxRouteAlternatives()),
                    List.of("route-proposal-budget-disabled"));
        }
        List<String> reasons = new ArrayList<>();
        String machineProfile = properties.getCompute().getAdaptive().getMachineProfile();
        String profileName = properties.getCompute().getAdaptive().getProfileName();
        String size = inferredSize(request, bundleCount, driverCandidateCount);
        int maxTotal = maxTotalFor(budget, machineProfile, profileName, size);
        String mode = modeFor(machineProfile, profileName, size);
        reasons.add("budget-mode-" + mode);
        if (previousGeometryCoverage > 0.0 && previousGeometryCoverage < budget.getLowGeometryCoverageThreshold()) {
            maxTotal = Math.max(1, (int) Math.floor(maxTotal * budget.getLowGeometryCoverageBreadthMultiplier()));
            reasons.add("low-geometry-coverage-breadth-reduced");
        }
        if (etaContext != null && etaContext.weatherBadSignal()) {
            maxTotal = Math.max(1, (int) Math.ceil(maxTotal * 1.15));
            reasons.add("weather-risk-budget-expanded");
        }
        if (etaContext != null && etaContext.trafficBadSignal()) {
            maxTotal = Math.max(1, (int) Math.ceil(maxTotal * 1.15));
            reasons.add("traffic-risk-budget-expanded");
        }
        if (bundleCount <= 1) {
            maxTotal = Math.min(maxTotal, Math.max(24, budget.getMaxDriversPerBundle() * budget.getMaxAlternativesPerTuple() * 4));
            reasons.add("small-bundle-pool-budget-capped");
        }
        return new RouteProposalBudgetDecision(
                true,
                mode,
                Math.max(1, maxTotal),
                Math.max(1, budget.getMaxDriversPerBundle()),
                Math.max(1, budget.getMaxAnchorsPerBundle()),
                Math.max(1, budget.getMaxAlternativesPerTuple()),
                List.copyOf(reasons.stream().distinct().toList()));
    }

    private int maxTotalFor(RouteChainDispatchV2Properties.Candidate.RouteProposalBudget budget,
                            String machineProfile,
                            String profileName,
                            String size) {
        if ("local-lite".equalsIgnoreCase(machineProfile)) {
            return budget.getLocalLiteMaxTotal();
        }
        if ("dispatch-v2-full-adaptive".equalsIgnoreCase(profileName) && "M".equals(size)) {
            return budget.getFullAdaptiveMMaxTotal();
        }
        return budget.getFullAdaptiveSMaxTotal();
    }

    private String modeFor(String machineProfile, String profileName, String size) {
        if ("local-lite".equalsIgnoreCase(machineProfile)) {
            return "local-lite";
        }
        if ("dispatch-v2-full-adaptive".equalsIgnoreCase(profileName)) {
            return "full-adaptive-" + size.toLowerCase(java.util.Locale.ROOT);
        }
        return "default-" + size.toLowerCase(java.util.Locale.ROOT);
    }

    private String inferredSize(DispatchV2Request request, int bundleCount, int driverCandidateCount) {
        int openOrderCount = request == null || request.openOrders() == null ? 0 : request.openOrders().size();
        int availableDriverCount = request == null || request.availableDrivers() == null ? 0 : request.availableDrivers().size();
        if (openOrderCount <= 24 && availableDriverCount <= 16) {
            return "S";
        }
        return bundleCount > 12 || driverCandidateCount > 96 ? "M" : "S";
    }
}
