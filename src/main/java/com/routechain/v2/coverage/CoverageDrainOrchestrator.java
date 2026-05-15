package com.routechain.v2.coverage;

import com.routechain.domain.Driver;
import com.routechain.domain.Order;
import com.routechain.v2.DispatchV2CompatibleCore;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.executor.DispatchAssignment;
import com.routechain.v2.quota.DriverLoadSummary;
import com.routechain.v2.quota.DriverQuotaBalancer;
import com.routechain.v2.unified.DispatchPolicy;
import com.routechain.v2.unified.DispatchStrategy;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class CoverageDrainOrchestrator {
    private final DispatchV2CompatibleCore dispatchCore;
    private final DriverQuotaBalancer quotaBalancer;
    private final CoverageRepairService repairService;
    private final CoverageValidator coverageValidator;

    public CoverageDrainOrchestrator(DispatchV2CompatibleCore dispatchCore) {
        this.dispatchCore = dispatchCore;
        this.quotaBalancer = new DriverQuotaBalancer();
        this.repairService = new CoverageRepairService();
        this.coverageValidator = new CoverageValidator();
    }

    public CoverageDrainResult drain(DispatchV2Request baseRequest, DispatchStrategy strategy, DispatchPolicy policy) {
        if (strategy == DispatchStrategy.CORE_ONLY || policy.coverageMode().name().equals("BEST_EFFORT")) {
            long started = System.nanoTime();
            DispatchV2Result result = dispatchCore.dispatch(baseRequest);
            long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
            Map<String, Integer> loads = loadsFromAssignments(baseRequest.availableDrivers(), result.assignments());
            CoverageSummary summary = coverageValidator.validate(baseRequest.openOrders(), result.assignments(), 0, Math.max(0, baseRequest.openOrders().size() - assignedOrderIds(result.assignments()).size()), true);
            return new CoverageDrainResult(result, summary, List.of(new PassSummary(1, "CORE_ONLY", baseRequest.openOrders().size(), baseRequest.availableDrivers().size(), assignedOrderIds(result.assignments()).size(), summary.uncoveredOrderCount(), runtimeMs)), quotaBalancer.summarize(baseRequest.availableDrivers(), loads, policy, baseRequest.openOrders().size()));
        }

        List<Order> remainingOrders = new ArrayList<>(baseRequest.openOrders());
        List<DispatchAssignment> finalAssignments = new ArrayList<>();
        List<PassSummary> passTimeline = new ArrayList<>();
        Map<String, Integer> driverLoads = quotaBalancer.emptyLoads(baseRequest.availableDrivers());
        DispatchV2Result lastResult = null;
        int maxOrders = policy.effectiveMaxOrdersPerDriver(baseRequest.openOrders().size(), baseRequest.availableDrivers().size());

        for (int pass = 1; pass <= Math.max(1, policy.maxPasses()) && !remainingOrders.isEmpty(); pass++) {
            List<Driver> eligibleDrivers = quotaBalancer.eligibleDrivers(baseRequest.availableDrivers(), driverLoads, maxOrders);
            if (eligibleDrivers.isEmpty()) {
                break;
            }
            DispatchV2Request passRequest = new DispatchV2Request(
                    baseRequest.schemaVersion(),
                    baseRequest.traceId() + "-P" + pass,
                    remainingOrders,
                    eligibleDrivers,
                    baseRequest.regions(),
                    baseRequest.weatherProfile(),
                    baseRequest.decisionTime() == null ? Instant.now() : baseRequest.decisionTime().plusMillis(pass));
            long started = System.nanoTime();
            DispatchV2Result passResult = dispatchCore.dispatch(passRequest);
            long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
            lastResult = passResult;
            Set<String> newlyAssigned = new LinkedHashSet<>();
            for (DispatchAssignment assignment : passResult.assignments()) {
                List<String> acceptedOrderIds = assignment.orderIds().stream()
                        .filter(orderId -> remainingOrders.stream().anyMatch(order -> order.orderId().equals(orderId)))
                        .filter(orderId -> driverLoads.getOrDefault(assignment.driverId(), 0) < maxOrders)
                        .toList();
                if (acceptedOrderIds.isEmpty()) {
                    continue;
                }
                DispatchAssignment normalized = normalizeAssignment(assignment, acceptedOrderIds, pass, finalAssignments.size());
                finalAssignments.add(normalized);
                newlyAssigned.addAll(acceptedOrderIds);
                driverLoads.put(assignment.driverId(), driverLoads.getOrDefault(assignment.driverId(), 0) + acceptedOrderIds.size());
            }
            remainingOrders.removeIf(order -> newlyAssigned.contains(order.orderId()));
            passTimeline.add(new PassSummary(pass, "CORE_DISPATCH", passRequest.openOrders().size(), eligibleDrivers.size(), newlyAssigned.size(), remainingOrders.size(), runtimeMs));
            if (newlyAssigned.isEmpty()) {
                break;
            }
        }

        if (!remainingOrders.isEmpty() && policy.balancedRepairEnabled()) {
            int before = assignedOrderIds(finalAssignments).size();
            finalAssignments = repairService.repair(finalAssignments, baseRequest.openOrders(), baseRequest.availableDrivers(), driverLoads, maxOrders);
            Set<String> assigned = assignedOrderIds(finalAssignments);
            remainingOrders.removeIf(order -> assigned.contains(order.orderId()));
            passTimeline.add(new PassSummary(passTimeline.size() + 1, "BALANCED_COVERAGE_REPAIR", remainingOrders.size() + assigned.size() - before, baseRequest.availableDrivers().size(), Math.max(0, assigned.size() - before), remainingOrders.size(), 0));
        }

        if (!remainingOrders.isEmpty() && policy.singletonFallbackEnabled()) {
            int assignedBefore = assignedOrderIds(finalAssignments).size();
            for (Order order : List.copyOf(remainingOrders)) {
                List<Driver> eligibleDrivers = quotaBalancer.eligibleDrivers(baseRequest.availableDrivers(), driverLoads, Integer.MAX_VALUE);
                if (eligibleDrivers.isEmpty()) {
                    break;
                }
                Driver driver = eligibleDrivers.getFirst();
                finalAssignments.add(repairService.singletonFallback(order, driver, finalAssignments.size()));
                driverLoads.put(driver.driverId(), driverLoads.getOrDefault(driver.driverId(), 0) + 1);
                remainingOrders.remove(order);
            }
            passTimeline.add(new PassSummary(passTimeline.size() + 1, "SINGLETON_FALLBACK", remainingOrders.size() + assignedOrderIds(finalAssignments).size() - assignedBefore, baseRequest.availableDrivers().size(), Math.max(0, assignedOrderIds(finalAssignments).size() - assignedBefore), remainingOrders.size(), 0));
        }

        DispatchV2Result result = lastResult == null ? dispatchCore.dispatch(baseRequest) : lastResult;
        List<String> reasons = new ArrayList<>(result.degradeReasons());
        reasons.add("coverage-mode-core-multi-pass-full-coverage");
        reasons.add("dashboard-repair-disabled-core-owned-coverage");
        DispatchV2Result mergedResult = result.withAssignments(mergeByDriver(finalAssignments), reasons);
        CoverageSummary summary = coverageValidator.validate(baseRequest.openOrders(), mergedResult.assignments(), 0, remainingOrders.size(), true);
        List<DriverLoadSummary> loadSummary = quotaBalancer.summarize(baseRequest.availableDrivers(), driverLoads, policy, baseRequest.openOrders().size());
        return new CoverageDrainResult(mergedResult, summary, passTimeline, loadSummary);
    }

    private static DispatchAssignment normalizeAssignment(DispatchAssignment assignment, List<String> acceptedOrderIds, int pass, int rank) {
        return new DispatchAssignment(
                assignment.schemaVersion(),
                assignment.assignmentId() + "-P" + pass,
                assignment.proposalId(),
                assignment.bundleId() == null ? "core-pass-" + pass + "-" + assignment.driverId() : assignment.bundleId() + "-P" + pass,
                acceptedOrderIds.getFirst(),
                assignment.driverId(),
                acceptedOrderIds,
                assignment.stopOrder().stream().filter(stop -> acceptedOrderIds.stream().anyMatch(stop::contains)).toList(),
                assignment.actionType(),
                assignment.routeSource(),
                rank,
                assignment.selectionScore(),
                assignment.robustUtility(),
                assignment.projectedPickupEtaMinutes(),
                assignment.projectedCompletionEtaMinutes(),
                assignment.routeValue(),
                AssignmentSource.MULTI_PASS_SELECTED.name(),
                assignment.boundaryCross(),
                assignment.readyWindowStart(),
                assignment.readyWindowEnd(),
                appendReason(assignment.reasons(), "multi-pass-selected-pass-" + pass),
                assignment.degradeReasons());
    }

    private static List<DispatchAssignment> mergeByDriver(List<DispatchAssignment> assignments) {
        Map<String, List<DispatchAssignment>> byDriver = new LinkedHashMap<>();
        for (DispatchAssignment assignment : assignments) {
            byDriver.computeIfAbsent(assignment.driverId(), ignored -> new ArrayList<>()).add(assignment);
        }
        List<DispatchAssignment> merged = new ArrayList<>();
        int rank = 0;
        for (Map.Entry<String, List<DispatchAssignment>> entry : byDriver.entrySet()) {
            List<DispatchAssignment> group = entry.getValue();
            DispatchAssignment first = group.getFirst();
            List<String> orderIds = group.stream().flatMap(assignment -> assignment.orderIds().stream()).distinct().toList();
            List<String> stopOrder = group.stream().flatMap(assignment -> assignment.stopOrder().stream()).toList();
            List<String> reasons = group.stream().flatMap(assignment -> assignment.reasons().stream()).distinct().toList();
            merged.add(new DispatchAssignment(first.schemaVersion(), "merged-" + first.driverId(), first.proposalId(), "merged-batch-" + first.driverId(), orderIds.getFirst(), first.driverId(), orderIds, stopOrder, first.actionType(), first.routeSource(), rank++, first.selectionScore(), first.robustUtility(), first.projectedPickupEtaMinutes(), group.stream().mapToDouble(DispatchAssignment::projectedCompletionEtaMinutes).sum(), first.routeValue(), AssignmentSource.MULTI_PASS_SELECTED.name(), first.boundaryCross(), first.readyWindowStart(), first.readyWindowEnd(), appendReason(reasons, "core-merged-multi-pass-route"), group.stream().flatMap(assignment -> assignment.degradeReasons().stream()).distinct().toList()));
        }
        return merged;
    }

    private static Map<String, Integer> loadsFromAssignments(List<Driver> drivers, List<DispatchAssignment> assignments) {
        Map<String, Integer> loads = new LinkedHashMap<>();
        drivers.forEach(driver -> loads.put(driver.driverId(), 0));
        assignments.forEach(assignment -> loads.put(assignment.driverId(), loads.getOrDefault(assignment.driverId(), 0) + assignment.orderIds().size()));
        return loads;
    }

    private static Set<String> assignedOrderIds(List<DispatchAssignment> assignments) {
        Set<String> assigned = new LinkedHashSet<>();
        assignments.forEach(assignment -> assigned.addAll(assignment.orderIds()));
        return assigned;
    }

    private static List<String> appendReason(List<String> reasons, String reason) {
        List<String> next = new ArrayList<>(reasons == null ? List.of() : reasons);
        next.add(reason);
        return next.stream().distinct().toList();
    }
}
