package com.routechain.api.bigdata;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class LivePdLnsPostSolverImprover {
    Result improve(List<Map<String, Object>> selectedOrders, List<Map<String, Object>> assignments, double initialCost, double coreFinalCost, String solverPolicy, double breakRisk) {
        long started = System.nanoTime();
        GuardSnapshot preGuard = preGuard(selectedOrders, assignments, initialCost, coreFinalCost, breakRisk);
        if (preGuard.passed() && breakRisk < 0.20 && coreFinalCost <= initialCost + 1e-9) {
            long runtimeMs = Math.max(1L, (System.nanoTime() - started) / 1_000_000L);
            GuardSnapshot postGuard = preGuard.asStage("post-guard-skip-repair", "commit-core-incumbent", false);
            return new Result(
                    "PD_LNS_PNS_DEEP",
                    true,
                    true,
                    List.of(),
                    0,
                    0,
                    runtimeMs,
                    round(coreFinalCost),
                    round(improvementPercent(initialCost, coreFinalCost)),
                    0.0,
                    0.0,
                    0.0,
                    "pre-guard-pass-repair-skipped",
                    preGuard,
                    postGuard,
                    false,
                    true);
        }
        int maxIterations = iterationBudget(selectedOrders, solverPolicy, breakRisk);
        List<Map<String, Object>> incumbent = deadlineFirstRoute(selectedOrders);
        Cost incumbentCost = routeCost(incumbent);
        List<Map<String, Object>> best = new ArrayList<>(incumbent);
        Cost bestCost = incumbentCost;
        List<String> usedOperators = new ArrayList<>();
        int acceptedMoves = 0;

        for (int iteration = 0; iteration < maxIterations; iteration++) {
            String destroy = destroyOperator(iteration, best, breakRisk);
            String repair = repairOperator(iteration, breakRisk);
            usedOperators.add(destroy + "+" + repair);
            Destroyed destroyed = destroy(best, destroy, iteration);
            List<Map<String, Object>> candidate = repair(destroyed.remaining(), destroyed.removed(), repair);
            candidate = localSearch(candidate);
            Cost candidateCost = routeCost(candidate);
            if (candidateCost.safetyPassed() && accept(candidateCost, bestCost, iteration)) {
                best = candidate;
                bestCost = candidateCost;
                acceptedMoves++;
            }
        }

        double algorithmicFinalCost = bestCost.total();
        boolean repairWins = algorithmicFinalCost <= coreFinalCost + 1e-9;
        double finalCost = repairWins ? algorithmicFinalCost : coreFinalCost;
        GuardSnapshot postGuard = repairWins
                ? postRepairGuard(bestCost, selectedOrders, assignments, coreFinalCost, algorithmicFinalCost, breakRisk)
                : preGuard.asStage("post-guard-core-incumbent", preGuard.passed() ? "rollback-to-core-incumbent" : "rollback-blocked-core-incumbent", true);
        boolean safetyPassed = postGuard.passed();
        boolean accepted = safetyPassed && finalCost <= coreFinalCost + 1e-9;
        long runtimeMs = Math.max(1L, (System.nanoTime() - started) / 1_000_000L);
        return new Result(
                "PD_LNS_PNS_DEEP",
                accepted,
                safetyPassed,
                compactOperators(usedOperators),
                maxIterations,
                acceptedMoves,
                runtimeMs,
                round(finalCost),
                round(improvementPercent(initialCost, finalCost)),
                round(bestCost.distanceKm()),
                round(bestCost.latenessPenalty()),
                round(bestCost.detourPenalty()),
                accepted ? (repairWins ? "accepted-post-guard-repair" : "rollback-to-safe-core-incumbent") : "post-guard-blocked-commit",
                preGuard,
                postGuard,
                !repairWins,
                false);
    }

    private List<Map<String, Object>> deadlineFirstRoute(List<Map<String, Object>> orders) {
        return orders.stream()
                .sorted(Comparator.comparingDouble((Map<String, Object> order) -> number(order, "promisedEtaMinutes", 45.0))
                        .thenComparing(Comparator.comparingDouble(this::priorityScore).reversed()))
                .toList();
    }

    private Destroyed destroy(List<Map<String, Object>> route, String operator, int iteration) {
        if (route.size() <= 2) return new Destroyed(new ArrayList<>(route), List.of());
        int removeCount = Math.max(1, Math.min(route.size() / 3, 3));
        List<Map<String, Object>> sorted = new ArrayList<>(route);
        if ("late-order-removal".equals(operator)) {
            sorted.sort(Comparator.comparingDouble(this::latenessRisk).reversed());
        } else if ("shaw-related-removal".equals(operator)) {
            Map<String, Object> seed = route.get(iteration % route.size());
            sorted.sort(Comparator.<Map<String, Object>>comparingDouble(order -> relatedness(seed, order)).reversed());
        } else if ("worst-removal".equals(operator)) {
            sorted.sort(Comparator.comparingDouble(this::singleOrderCost).reversed());
        } else {
            int start = iteration % Math.max(1, route.size() - removeCount + 1);
            sorted = new ArrayList<>(route.subList(start, start + removeCount));
        }
        List<Map<String, Object>> removed = new ArrayList<>(sorted.subList(0, Math.min(removeCount, sorted.size())));
        Set<Map<String, Object>> removedSet = new LinkedHashSet<>(removed);
        List<Map<String, Object>> remaining = route.stream().filter(order -> !removedSet.contains(order)).toList();
        return new Destroyed(new ArrayList<>(remaining), removed);
    }

    private List<Map<String, Object>> repair(List<Map<String, Object>> remaining, List<Map<String, Object>> removed, String operator) {
        List<Map<String, Object>> route = new ArrayList<>(remaining);
        List<Map<String, Object>> pending = new ArrayList<>(removed);
        while (!pending.isEmpty()) {
            Insertion best = null;
            for (Map<String, Object> order : pending) {
                Insertion insertion = bestInsertion(route, order);
                if (best == null || insertion.rank(operator) > best.rank(operator)) best = insertion;
            }
            if (best == null) break;
            route.add(best.position(), best.order());
            pending.remove(best.order());
        }
        return route;
    }

    private Insertion bestInsertion(List<Map<String, Object>> route, Map<String, Object> order) {
        double bestDelta = Double.MAX_VALUE;
        double secondDelta = Double.MAX_VALUE;
        int bestPosition = route.size();
        for (int position = 0; position <= route.size(); position++) {
            List<Map<String, Object>> candidate = new ArrayList<>(route);
            candidate.add(position, order);
            double delta = routeCost(candidate).total() - routeCost(route).total();
            if (delta < bestDelta) {
                secondDelta = bestDelta;
                bestDelta = delta;
                bestPosition = position;
            } else if (delta < secondDelta) {
                secondDelta = delta;
            }
        }
        return new Insertion(order, bestPosition, bestDelta, secondDelta == Double.MAX_VALUE ? bestDelta : secondDelta);
    }

    private List<Map<String, Object>> localSearch(List<Map<String, Object>> route) {
        List<Map<String, Object>> best = new ArrayList<>(route);
        Cost bestCost = routeCost(best);
        boolean improved = true;
        int passes = 0;
        while (improved && passes++ < 3) {
            improved = false;
            for (int i = 0; i < best.size(); i++) {
                for (int j = i + 1; j < best.size(); j++) {
                    List<Map<String, Object>> swapped = new ArrayList<>(best);
                    Map<String, Object> temp = swapped.get(i);
                    swapped.set(i, swapped.get(j));
                    swapped.set(j, temp);
                    Cost cost = routeCost(swapped);
                    if (cost.safetyPassed() && cost.total() + 1e-9 < bestCost.total()) {
                        best = swapped;
                        bestCost = cost;
                        improved = true;
                    }
                }
            }
        }
        return best;
    }

    private Cost routeCost(List<Map<String, Object>> route) {
        double distance = 0.0;
        double elapsed = 0.0;
        double latePenalty = 0.0;
        double detourPenalty = 0.0;
        double urgencyPenalty = 0.0;
        Map<String, Object> previous = null;
        boolean normalBeforeUrgent = false;
        for (Map<String, Object> order : route) {
            if (previous != null) {
                double link = haversineKm(number(previous, "dropoffLat", 0.0), number(previous, "dropoffLng", 0.0), number(order, "pickupLat", 0.0), number(order, "pickupLng", 0.0));
                distance += link;
                elapsed += link * 2.4;
            }
            double leg = orderKm(order);
            distance += leg;
            elapsed += leg * 2.4 + 1.0;
            double eta = number(order, "promisedEtaMinutes", 45.0);
            latePenalty += Math.max(0.0, elapsed - eta) * 8.0;
            detourPenalty += Math.max(0.0, leg - 3.0) * 0.4;
            if (urgent(order) && normalBeforeUrgent) urgencyPenalty += 25.0;
            if (!urgent(order)) normalBeforeUrgent = true;
            previous = order;
        }
        double total = distance + latePenalty + detourPenalty + urgencyPenalty;
        return new Cost(total, distance, latePenalty, detourPenalty + urgencyPenalty, latePenalty == 0.0 && urgencyPenalty == 0.0);
    }

    private boolean accept(Cost candidate, Cost best, int iteration) {
        if (candidate.total() + 1e-9 < best.total()) return true;
        double temperature = Math.max(0.01, 0.20 / (iteration + 1));
        return candidate.safetyPassed() && candidate.total() <= best.total() * (1.0 + temperature);
    }

    private int iterationBudget(List<Map<String, Object>> selectedOrders, String solverPolicy, double breakRisk) {
        int base = selectedOrders.stream().anyMatch(this::urgent) ? 24 : 40;
        if (solverPolicy != null && solverPolicy.contains("BULK")) base += 40;
        base += (int) Math.round(Math.min(40.0, breakRisk * 40.0));
        return Math.max(8, Math.min(160, base));
    }

    private String destroyOperator(int iteration, List<Map<String, Object>> route, double breakRisk) {
        if (route.stream().anyMatch(this::urgent)) return iteration % 2 == 0 ? "urgent-risk-removal" : "late-order-removal";
        if (breakRisk >= 0.35) return iteration % 2 == 0 ? "worst-removal" : "shaw-related-removal";
        return switch (iteration % 4) {
            case 0 -> "worst-removal";
            case 1 -> "shaw-related-removal";
            case 2 -> "segment-removal";
            default -> "late-order-removal";
        };
    }

    private String repairOperator(int iteration, double breakRisk) {
        if (breakRisk >= 0.35) return iteration % 2 == 0 ? "regret-3" : "deadline-first";
        return iteration % 3 == 0 ? "regret-2" : iteration % 3 == 1 ? "cheapest-insertion" : "deadline-first";
    }

    private List<String> compactOperators(List<String> operators) {
        return operators.stream().distinct().limit(8).toList();
    }

    private boolean safetyPassed(List<Map<String, Object>> selectedOrders, List<Map<String, Object>> assignments) {
        if (assignments.isEmpty() && !selectedOrders.isEmpty()) return false;
        return selectedOrders.stream().noneMatch(order -> number(order, "promisedEtaMinutes", 45.0) <= 0.0);
    }

    private GuardSnapshot preGuard(List<Map<String, Object>> selectedOrders, List<Map<String, Object>> assignments, double initialCost, double coreFinalCost, double breakRisk) {
        List<String> reasons = new ArrayList<>();
        if (assignments.isEmpty() && !selectedOrders.isEmpty()) reasons.add("missing-core-assignment");
        if (selectedOrders.stream().anyMatch(order -> number(order, "promisedEtaMinutes", 45.0) <= 0.0)) reasons.add("invalid-sla");
        if (!Double.isFinite(initialCost) || !Double.isFinite(coreFinalCost)) reasons.add("invalid-cost");
        if (breakRisk >= 0.35) reasons.add("break-risk-high");
        boolean passed = reasons.isEmpty();
        return new GuardSnapshot("pre-guard", passed, passed ? "commit-or-skip-repair" : "repair-required", false, List.copyOf(reasons), round(coreFinalCost), 0.0, 0.0, round(breakRisk));
    }

    private GuardSnapshot postRepairGuard(Cost repairCost, List<Map<String, Object>> selectedOrders, List<Map<String, Object>> assignments, double coreFinalCost, double repairFinalCost, double breakRisk) {
        List<String> reasons = new ArrayList<>();
        if (!repairCost.safetyPassed()) reasons.add("route-hard-guard-failed");
        if (!safetyPassed(selectedOrders, assignments)) reasons.add("assignment-guard-failed");
        if (repairFinalCost > coreFinalCost + 1e-9) reasons.add("no-regress-cost-failed");
        boolean passed = reasons.isEmpty();
        return new GuardSnapshot("post-guard-repair", passed, passed ? "commit-repaired-route" : "rollback-to-incumbent-or-requeue", !passed, List.copyOf(reasons), round(repairFinalCost), round(repairCost.latenessPenalty()), round(repairCost.detourPenalty()), round(breakRisk));
    }

    private double singleOrderCost(Map<String, Object> order) { return orderKm(order) + latenessRisk(order) * 5.0; }
    private double latenessRisk(Map<String, Object> order) { return Math.max(0.0, 45.0 - number(order, "promisedEtaMinutes", 45.0)) / 45.0; }
    private double priorityScore(Map<String, Object> order) { return (urgent(order) ? 100.0 : 0.0) + number(order, "priority", 1.0) * 10.0; }
    private double relatedness(Map<String, Object> seed, Map<String, Object> order) { return 1.0 / (1.0 + haversineKm(number(seed, "pickupLat", 0.0), number(seed, "pickupLng", 0.0), number(order, "pickupLat", 0.0), number(order, "pickupLng", 0.0))); }
    private boolean urgent(Map<String, Object> order) { return Boolean.TRUE.equals(order.get("urgent")) || "true".equalsIgnoreCase(String.valueOf(order.get("urgent"))); }
    private double orderKm(Map<String, Object> order) { return haversineKm(number(order, "pickupLat", 0.0), number(order, "pickupLng", 0.0), number(order, "dropoffLat", 0.0), number(order, "dropoffLng", 0.0)); }

    private double haversineKm(double lat1, double lng1, double lat2, double lng2) {
        double earthKm = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2.0) * Math.sin(dLat / 2.0)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2.0) * Math.sin(dLng / 2.0);
        return earthKm * 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));
    }

    private double number(Map<String, Object> item, String key, double fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private double improvementPercent(double initialCost, double finalCost) { return initialCost <= 0.0 ? 0.0 : Math.max(0.0, (initialCost - finalCost) * 100.0 / initialCost); }
    private double round(double value) { return Math.round(value * 100.0) / 100.0; }

    record Result(String repairMode, boolean accepted, boolean safetyPassed, List<String> operators, int iterations, int acceptedMoves, long runtimeMs, double finalCost, double improvementPercent, double distanceKm, double latenessPenalty, double detourPenalty, String reason, GuardSnapshot preGuard, GuardSnapshot postGuard, boolean rollbackApplied, boolean repairSkipped) {
        Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("repairMode", repairMode);
            map.put("accepted", accepted);
            map.put("safetyPassed", safetyPassed);
            map.put("operators", operators);
            map.put("iterations", iterations);
            map.put("acceptedMoves", acceptedMoves);
            map.put("runtimeMs", runtimeMs);
            map.put("finalCost", finalCost);
            map.put("improvementPercent", improvementPercent);
            map.put("distanceKm", distanceKm);
            map.put("latenessPenalty", latenessPenalty);
            map.put("detourPenalty", detourPenalty);
            map.put("reason", reason);
            map.put("preGuard", preGuard.asMap());
            map.put("postGuard", postGuard.asMap());
            map.put("rollbackApplied", rollbackApplied);
            map.put("repairSkipped", repairSkipped);
            return map;
        }
    }

    record GuardSnapshot(String stage, boolean passed, String action, boolean rollbackApplied, List<String> reasons, double cost, double latenessPenalty, double detourPenalty, double breakRisk) {
        GuardSnapshot {
            reasons = reasons == null ? List.of() : List.copyOf(reasons);
        }
        GuardSnapshot asStage(String stage, String action, boolean rollbackApplied) {
            return new GuardSnapshot(stage, passed, action, rollbackApplied, reasons, cost, latenessPenalty, detourPenalty, breakRisk);
        }
        Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("stage", stage);
            map.put("passed", passed);
            map.put("action", action);
            map.put("rollbackApplied", rollbackApplied);
            map.put("reasons", reasons);
            map.put("cost", cost);
            map.put("latenessPenalty", latenessPenalty);
            map.put("detourPenalty", detourPenalty);
            map.put("breakRisk", breakRisk);
            return map;
        }
    }

    private record Destroyed(List<Map<String, Object>> remaining, List<Map<String, Object>> removed) {}
    private record Cost(double total, double distanceKm, double latenessPenalty, double detourPenalty, boolean safetyPassed) {}
    private record Insertion(Map<String, Object> order, int position, double bestDelta, double secondDelta) {
        double rank(String operator) {
            double regret = secondDelta - bestDelta;
            if ("regret-3".equals(operator) || "regret-2".equals(operator)) return regret * 10.0 - bestDelta;
            if ("deadline-first".equals(operator)) return -bestDelta + 2.0;
            return -bestDelta;
        }
    }
}
