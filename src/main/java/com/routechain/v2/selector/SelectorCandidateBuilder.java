package com.routechain.v2.selector;

import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.bundle.BundleCandidate;
import com.routechain.v2.constraints.ConstraintCheckResult;
import com.routechain.v2.constraints.FeasibilityOracle;
import com.routechain.v2.route.DispatchCandidateContext;
import com.routechain.v2.route.DispatchRouteCandidateStage;
import com.routechain.v2.route.DispatchRouteProposalStage;
import com.routechain.v2.route.DriverCandidate;
import com.routechain.v2.route.PickupAnchor;
import com.routechain.v2.route.RouteProposal;
import com.routechain.v2.route.RouteProposalSource;
import com.routechain.v2.route.RouteShapeAnalysis;
import com.routechain.v2.route.RouteShapeQuality;
import com.routechain.v2.optimizer.HybridOptimizerObjective;
import com.routechain.v2.scenario.DispatchScenarioStage;
import com.routechain.v2.scenario.RobustUtility;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class SelectorCandidateBuilder {
    private static final double WEAK_BOUNDARY_SUPPORT_THRESHOLD = 0.60;

    private final RouteChainDispatchV2Properties properties;
    private final FeasibilityOracle feasibilityOracle;

    public SelectorCandidateBuilder(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
        this.feasibilityOracle = new FeasibilityOracle();
    }

    public SelectorCandidateBuildResult build(DispatchRouteProposalStage routeProposalStage,
                                              DispatchScenarioStage scenarioStage,
                                              DispatchRouteCandidateStage routeCandidateStage,
                                              DispatchCandidateContext context) {
        Map<String, RobustUtility> robustUtilityByProposalId = scenarioStage.robustUtilities().stream()
                .collect(java.util.stream.Collectors.toMap(RobustUtility::proposalId, utility -> utility, (left, right) -> left));
        Map<String, DriverCandidate> driverCandidateByKey = routeCandidateStage.driverCandidates().stream()
                .collect(java.util.stream.Collectors.toMap(
                        candidate -> driverKey(candidate.bundleId(), candidate.anchorOrderId(), candidate.driverId()),
                        candidate -> candidate,
                        (left, right) -> left));
        Map<String, PickupAnchor> pickupAnchorByKey = routeCandidateStage.pickupAnchors().stream()
                .collect(java.util.stream.Collectors.toMap(
                        anchor -> anchorKey(anchor.bundleId(), anchor.anchorOrderId()),
                        anchor -> anchor,
                        (left, right) -> left));

        Map<SelectorCandidateIdentityKey, SelectorCandidateEnvelope> bestByIdentity = new LinkedHashMap<>();
        List<SelectorTraceEvent> missingContextSkips = new ArrayList<>();
        List<String> degradeReasons = new ArrayList<>();

        for (RouteProposal proposal : routeProposalStage.routeProposals()) {
            if (isDominatedBySameOrderSetAlternative(proposal, routeProposalStage.routeProposals())) {
                missingContextSkips.add(new SelectorTraceEvent(proposal.proposalId(), "selector-reject-dominated-route-shape"));
                degradeReasons.add("selector-reject-dominated-route-shape");
                continue;
            }
            RobustUtility robustUtility = robustUtilityByProposalId.get(proposal.proposalId());
            DriverCandidate driverCandidate = driverCandidateByKey.get(driverKey(proposal.bundleId(), proposal.anchorOrderId(), proposal.driverId()));
            BundleCandidate bundleCandidate = context.bundle(proposal.bundleId());
            PickupAnchor pickupAnchor = pickupAnchorByKey.get(anchorKey(proposal.bundleId(), proposal.anchorOrderId()));
            List<String> missing = missingContext(robustUtility, driverCandidate, bundleCandidate, pickupAnchor);
            if (!missing.isEmpty()) {
                missingContextSkips.add(new SelectorTraceEvent(proposal.proposalId(), String.join(",", missing)));
                degradeReasons.add("selector-missing-upstream-context");
                continue;
            }
            String shapeVerdict = RouteShapeQuality.verdict(proposal);
            boolean weakShape = shouldRejectWeakShape(proposal);
            if ("REJECT_SHAPE".equals(shapeVerdict)) {
                missingContextSkips.add(new SelectorTraceEvent(proposal.proposalId(), "selector-reject-zigzag-route"));
                degradeReasons.add("selector-reject-zigzag-route");
                continue;
            }
            if (weakShape) {
                missingContextSkips.add(new SelectorTraceEvent(proposal.proposalId(), "selector-reject-weak-shape-route"));
                degradeReasons.add("selector-reject-weak-shape-route");
                continue;
            }

            SelectorCandidate candidate = new SelectorCandidate(
                    "selector-candidate/v1",
                    proposal.proposalId(),
                    proposal.bundleId(),
                    proposal.anchorOrderId(),
                    proposal.driverId(),
                    List.copyOf(bundleCandidate.orderIds()),
                    robustUtility.robustUtility(),
                    proposal.routeValue(),
                    proposal.source(),
                    bundleCandidate.clusterId(),
                    bundleCandidate.boundaryCross(),
                    selectionScore(proposal, robustUtility, driverCandidate, context, shapeVerdict, weakShape),
                    proposal.feasible(),
                    buildReasons(proposal, driverCandidate),
                    List.copyOf(proposal.degradeReasons()));
            ConstraintCheckResult feasibility = feasibilityOracle.check(candidate);
            if (!feasibility.feasible()) {
                String reason = feasibility.violations().stream()
                        .map(com.routechain.v2.constraints.ConstraintViolation::code)
                        .collect(java.util.stream.Collectors.joining(","));
                missingContextSkips.add(new SelectorTraceEvent(proposal.proposalId(), reason));
                degradeReasons.add("selector-feasibility-oracle-rejected");
                continue;
            }
            SelectorCandidateEnvelope envelope = new SelectorCandidateEnvelope(candidate, proposal.projectedPickupEtaMinutes());
            SelectorCandidateIdentityKey identityKey = new SelectorCandidateIdentityKey(
                    proposal.bundleId(),
                    proposal.anchorOrderId(),
                    proposal.driverId(),
                    proposal.source(),
                    stopOrderSignature(proposal));
            SelectorCandidateEnvelope existing = bestByIdentity.get(identityKey);
            if (existing == null || isBetter(envelope, existing)) {
                bestByIdentity.put(identityKey, envelope);
            }
        }

        List<SelectorCandidateEnvelope> candidateEnvelopes = bestByIdentity.values().stream()
                .sorted(Comparator.comparing(envelope -> envelope.candidate().proposalId()))
                .toList();
        return new SelectorCandidateBuildResult(
                candidateEnvelopes,
                degradeReasons.stream().distinct().toList(),
                new SelectorDecisionTrace(List.copyOf(missingContextSkips), List.of(), List.of()));
    }

    private List<String> buildReasons(RouteProposal proposal, DriverCandidate driverCandidate) {
        List<String> reasons = new ArrayList<>(proposal.reasons());
        reasons.add("selector-score-from-robust-utility");
        if (driverCandidate.rerankScore() >= 0.7) {
            reasons.add("selector-rerank-support-strong");
        }
        if (proposal.source() == RouteProposalSource.FALLBACK_SIMPLE) {
            reasons.add("selector-fallback-penalty-applied");
        }
        if (proposal.geometryAvailable()) {
            reasons.add("selector-route-vector-tie-break-available");
        }
        reasons.addAll(RouteShapeQuality.reasons(proposal));
        RouteShapeAnalysis analysis = RouteShapeQuality.analyze(proposal);
        if (!"UNKNOWN".equals(analysis.verdict())) {
            reasons.add("route-shape-verdict-" + analysis.verdict().toLowerCase(java.util.Locale.ROOT).replace('_', '-'));
        }
        if (analysis.detourRatio() > RouteShapeQuality.DETOUR_WEAK_RATIO) {
            reasons.add("selector-detour-guard-active");
        }
        return List.copyOf(reasons);
    }

    private List<String> missingContext(RobustUtility robustUtility,
                                        DriverCandidate driverCandidate,
                                        BundleCandidate bundleCandidate,
                                        PickupAnchor pickupAnchor) {
        List<String> missing = new ArrayList<>();
        if (robustUtility == null) {
            missing.add("robust-utility");
        }
        if (driverCandidate == null) {
            missing.add("driver-candidate");
        }
        if (bundleCandidate == null) {
            missing.add("bundle-candidate");
        }
        if (pickupAnchor == null) {
            missing.add("pickup-anchor");
        }
        return missing;
    }

    private double selectionScore(RouteProposal proposal,
                                  RobustUtility robustUtility,
                                  DriverCandidate driverCandidate,
                                  DispatchCandidateContext context,
                                  String shapeVerdict,
                                  boolean weakShape) {
        double score = HybridOptimizerObjective.selectorScore(
                proposal,
                robustUtility,
                driverCandidate,
                context,
                properties.getSelector().getFallbackPenalty());
        score += bundleSizeLift(proposal);
        RouteShapeAnalysis analysis = RouteShapeQuality.analyze(proposal);
        if (context.bundle(proposal.bundleId()) != null
                && context.bundle(proposal.bundleId()).boundaryCross()
                && context.acceptedBoundarySupport(proposal.bundleId()) < WEAK_BOUNDARY_SUPPORT_THRESHOLD) {
            score -= 0.02;
        }
        if (proposal.source() == RouteProposalSource.FALLBACK_SIMPLE && "REJECT_SHAPE".equals(analysis.verdict())) {
            score -= 0.08;
        }
        if ("REJECT_SHAPE".equals(shapeVerdict)) {
            score -= 0.20;
        } else if ("WEAK_SHAPE".equals(shapeVerdict) || weakShape) {
            score -= 0.10;
        }
        return score;
    }

    private double bundleSizeLift(RouteProposal proposal) {
        int bundleSize = proposal.stopOrder().size();
        RouteShapeAnalysis analysis = RouteShapeQuality.analyze(proposal);
        if (bundleSize <= 2) {
            if (bundleSize < 2) {
                return 0.0;
            }
            return proposal.straightnessScore() < 0.55 || analysis.detourRatio() > RouteShapeQuality.DETOUR_WEAK_RATIO ? -0.04 : 0.28;
        }
        double shapeGuard = proposal.straightnessScore() >= 0.62
                && proposal.turnCount() <= (7 * bundleSize + 6)
                && analysis.detourRatio() <= 1.55
                && analysis.backtrackCount() == 0 ? 1.0 : 0.0;
        if (shapeGuard == 0.0) {
            return 0.0;
        }
        double compactShapeBonus = Math.min(0.06, Math.max(0.0, analysis.shapeScore() - 0.65) * 0.12);
        double coverageLift = 0.22 * (bundleSize - 2);
        return Math.min(0.62, coverageLift + compactShapeBonus);
    }

    private boolean shouldRejectWeakShape(RouteProposal proposal) {
        RouteShapeAnalysis analysis = RouteShapeQuality.analyze(proposal);
        if (!"WEAK_SHAPE".equals(analysis.verdict()) || proposal.stopOrder().size() <= 1) {
            return false;
        }
        return proposal.straightnessScore() < RouteShapeQuality.MULTI_ORDER_STRAIGHTNESS_WEAK_FLOOR
                || proposal.turnCount() > RouteShapeQuality.MULTI_ORDER_TURN_WEAK_LIMIT
                || analysis.detourRatio() > RouteShapeQuality.DETOUR_REJECT_RATIO
                || (proposal.congestionScore() >= RouteShapeQuality.CONGESTION_SELECTED_REJECT_RISK && proposal.straightnessScore() < 0.70);
    }

    private boolean isDominatedBySameOrderSetAlternative(RouteProposal proposal, List<RouteProposal> routeProposals) {
        if (proposal == null || proposal.stopOrder().size() <= 1) {
            return false;
        }
        return routeProposals.stream()
                .filter(other -> other != proposal)
                .filter(other -> other.driverId().equals(proposal.driverId()))
                .anyMatch(other -> RouteShapeQuality.dominates(other, proposal));
    }

    private boolean isBetter(SelectorCandidateEnvelope candidate, SelectorCandidateEnvelope existing) {
        if (candidate.candidate().selectionScore() != existing.candidate().selectionScore()) {
            return candidate.candidate().selectionScore() > existing.candidate().selectionScore();
        }
        if (candidate.candidate().robustUtility() != existing.candidate().robustUtility()) {
            return candidate.candidate().robustUtility() > existing.candidate().robustUtility();
        }
        if (candidate.projectedPickupEtaMinutes() != existing.projectedPickupEtaMinutes()) {
            return candidate.projectedPickupEtaMinutes() < existing.projectedPickupEtaMinutes();
        }
        double candidateVectorTieBreak = routeVectorTieBreak(candidate.candidate());
        double existingVectorTieBreak = routeVectorTieBreak(existing.candidate());
        if (candidateVectorTieBreak != existingVectorTieBreak) {
            return candidateVectorTieBreak > existingVectorTieBreak;
        }
        return candidate.candidate().proposalId().compareTo(existing.candidate().proposalId()) < 0;
    }

    private double routeVectorTieBreak(SelectorCandidate candidate) {
        return candidate.reasons().contains("selector-route-vector-tie-break-available") ? 1.0 : 0.0;
    }

    private String driverKey(String bundleId, String anchorOrderId, String driverId) {
        return bundleId + "|" + anchorOrderId + "|" + driverId;
    }

    private String anchorKey(String bundleId, String anchorOrderId) {
        return bundleId + "|" + anchorOrderId;
    }

    private String stopOrderSignature(RouteProposal proposal) {
        return proposal.stopOrder().stream().filter(Objects::nonNull).collect(java.util.stream.Collectors.joining(">"));
    }
}
