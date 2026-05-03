package com.routechain.v2.executor;

import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.bundle.BundleFamily;
import com.routechain.v2.bundle.BundleProposalSource;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.PickupAnchor;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.selector.SelectedProposal;
import com.routechain.v2.selector.SelectorCandidate;

import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class SelectedProposalResolver {

    public SelectedProposalResolveResult resolve(SelectedProposal selectedProposal,
                                                 Map<String, SelectorCandidate> selectorCandidateByProposalId,
                                                 Map<String, RouteProposal> routeProposalByProposalId,
                                                 DispatchRouteCandidateStage routeCandidateStage,
                                                 DispatchCandidateContext context) {
        SelectorCandidate selectorCandidate = selectorCandidateByProposalId.get(selectedProposal.proposalId());
        RouteProposal routeProposal = routeProposalByProposalId.get(selectedProposal.proposalId());
        BundleCandidate bundleCandidate = selectorCandidate == null ? null : context.bundle(selectorCandidate.bundleId());
        PickupAnchor pickupAnchor = selectorCandidate == null ? null : routeCandidateStage.pickupAnchors().stream()
                .filter(anchor -> anchor.bundleId().equals(selectorCandidate.bundleId())
                        && anchor.anchorOrderId().equals(selectorCandidate.anchorOrderId()))
                .findFirst()
                .orElse(null);
        DriverCandidate driverCandidate = selectorCandidate == null ? null : routeCandidateStage.driverCandidates().stream()
                .filter(candidate -> candidate.bundleId().equals(selectorCandidate.bundleId())
                        && candidate.anchorOrderId().equals(selectorCandidate.anchorOrderId())
                        && candidate.driverId().equals(selectorCandidate.driverId()))
                .findFirst()
                .orElse(null);

        if (selectorCandidate == null || routeProposal == null || bundleCandidate == null || pickupAnchor == null || driverCandidate == null) {
            if (selectorCandidate != null && selectorCandidate.source() == RouteProposalSource.ACTIVE_ROUTE_INSERTION) {
                return activeRouteInsertionResolution(selectedProposal, selectorCandidate);
            }
            return new SelectedProposalResolveResult(
                    Optional.empty(),
                    new DispatchExecutionTrace(
                            List.of(selectedProposal.proposalId()),
                            List.of(),
                            List.of(),
                            List.of(),
                            List.of(),
                            "selected-proposal-missing-context"),
                    List.of("executor-missing-selected-proposal-context"));
        }

        return new SelectedProposalResolveResult(
                Optional.of(new ResolvedSelectedProposal(
                        selectedProposal,
                        selectorCandidate,
                        routeProposal,
                        bundleCandidate,
                        pickupAnchor,
                        driverCandidate)),
                new DispatchExecutionTrace(
                        List.of(),
                        List.of(),
                        List.of("resolved:" + selectedProposal.proposalId()),
                        List.of(),
                        List.of(),
                        "selected-proposal-resolved"),
                List.of());
    }

    private SelectedProposalResolveResult activeRouteInsertionResolution(SelectedProposal selectedProposal,
                                                                         SelectorCandidate selectorCandidate) {
        BundleCandidate bundleCandidate = new BundleCandidate(
                "bundle-candidate/v1",
                selectorCandidate.bundleId(),
                BundleProposalSource.DETERMINISTIC_FAMILY,
                BundleFamily.ACTIVE_ROUTE_ADDON,
                selectorCandidate.clusterId(),
                selectorCandidate.boundaryCross(),
                List.of(),
                selectorCandidate.orderIds(),
                String.join("|", selectorCandidate.orderIds().stream().sorted().toList()),
                selectorCandidate.anchorOrderId(),
                "active-route",
                selectorCandidate.selectionScore(),
                selectorCandidate.feasible(),
                selectorCandidate.degradeReasons());
        PickupAnchor pickupAnchor = new PickupAnchor(
                "pickup-anchor/v1",
                selectorCandidate.bundleId(),
                bundleCandidate.orderSetSignature(),
                selectorCandidate.anchorOrderId(),
                0,
                selectorCandidate.selectionScore(),
                List.of("active-route-insertion-synthetic-anchor"));
        DriverCandidate driverCandidate = new DriverCandidate(
                "driver-candidate/v1",
                selectorCandidate.bundleId(),
                selectorCandidate.anchorOrderId(),
                selectorCandidate.driverId(),
                0,
                0.0,
                selectorCandidate.robustUtility(),
                selectorCandidate.selectionScore(),
                List.of("active-route-insertion-synthetic-driver"),
                selectorCandidate.degradeReasons());
        RouteProposal routeProposal = new RouteProposal(
                "route-proposal/v1",
                selectorCandidate.proposalId(),
                selectorCandidate.bundleId(),
                selectorCandidate.anchorOrderId(),
                selectorCandidate.driverId(),
                RouteProposalSource.ACTIVE_ROUTE_INSERTION,
                selectorCandidate.orderIds(),
                0.0,
                0.0,
                selectorCandidate.routeValue(),
                selectorCandidate.feasible(),
                List.of("active-route-insertion-synthetic-route-proposal"),
                selectorCandidate.degradeReasons());
        return new SelectedProposalResolveResult(
                Optional.of(new ResolvedSelectedProposal(
                        selectedProposal,
                        selectorCandidate,
                        routeProposal,
                        bundleCandidate,
                        pickupAnchor,
                        driverCandidate)),
                new DispatchExecutionTrace(
                        List.of(),
                        List.of(),
                        List.of("resolved-active-route-insertion:" + selectedProposal.proposalId()),
                        List.of(),
                        List.of(),
                        "active-route-insertion-selected-proposal-resolved"),
                List.of("executor-active-route-insertion-context-synthesized"));
    }
}
