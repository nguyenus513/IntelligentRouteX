package com.routechain.v2.active;

import com.routechain.domain.GeoPoint;

import java.util.ArrayList;
import java.util.List;

public final class ActiveRouteSequenceRepairer {
    private static final int MAX_MOVES_TRIED = 48;

    public ActiveRouteSequenceRepairResult repair(GeoPoint currentLocation, List<ActiveRouteStop> initialSequence) {
        if (initialSequence == null || initialSequence.size() < 4) {
            return new ActiveRouteSequenceRepairResult(
                    "active-route-sequence-repair-result/v1",
                    initialSequence == null ? List.of() : initialSequence,
                    0,
                    0,
                    0.0,
                    List.of("active-sequence-repair-skipped-small-route"));
        }
        List<ActiveRouteStop> best = new ArrayList<>(initialSequence);
        double bestCost = geometryCost(currentLocation, best);
        int movesTried = 0;
        int movesAccepted = 0;
        boolean improved = true;
        while (improved && movesTried < MAX_MOVES_TRIED) {
            improved = false;
            RepairMove bestMove = null;
            for (int left = 0; left < best.size() - 1 && movesTried < MAX_MOVES_TRIED; left++) {
                List<ActiveRouteStop> swapped = adjacentSwap(best, left);
                movesTried++;
                if (precedenceFeasible(swapped)) {
                    double cost = geometryCost(currentLocation, swapped);
                    if (cost + 1e-9 < bestCost) {
                        bestMove = new RepairMove(swapped, cost);
                        bestCost = cost;
                    }
                }
            }
            for (int from = 0; from < best.size() && movesTried < MAX_MOVES_TRIED; from++) {
                for (int to = 0; to < best.size() && movesTried < MAX_MOVES_TRIED; to++) {
                    if (from == to) {
                        continue;
                    }
                    List<ActiveRouteStop> relocated = relocate(best, from, to);
                    movesTried++;
                    if (precedenceFeasible(relocated)) {
                        double cost = geometryCost(currentLocation, relocated);
                        if (cost + 1e-9 < bestCost) {
                            bestMove = new RepairMove(relocated, cost);
                            bestCost = cost;
                        }
                    }
                }
            }
            if (bestMove != null) {
                best = new ArrayList<>(bestMove.stopSequence());
                movesAccepted++;
                improved = true;
            }
        }
        double initialCost = geometryCost(currentLocation, initialSequence);
        double delta = initialCost - bestCost;
        List<String> reasons = movesAccepted > 0
                ? List.of("active-sequence-or-opt-repair-applied", "active-sequence-2opt-adjacent-repair-applied")
                : List.of("active-sequence-repair-no-improvement");
        return new ActiveRouteSequenceRepairResult(
                "active-route-sequence-repair-result/v1",
                best,
                movesTried,
                movesAccepted,
                delta,
                reasons);
    }

    private List<ActiveRouteStop> adjacentSwap(List<ActiveRouteStop> sequence, int left) {
        ArrayList<ActiveRouteStop> swapped = new ArrayList<>(sequence);
        ActiveRouteStop temp = swapped.get(left);
        swapped.set(left, swapped.get(left + 1));
        swapped.set(left + 1, temp);
        return List.copyOf(swapped);
    }

    private List<ActiveRouteStop> relocate(List<ActiveRouteStop> sequence, int from, int to) {
        ArrayList<ActiveRouteStop> relocated = new ArrayList<>(sequence);
        ActiveRouteStop stop = relocated.remove(from);
        relocated.add(Math.max(0, Math.min(to, relocated.size())), stop);
        return List.copyOf(relocated);
    }

    private boolean precedenceFeasible(List<ActiveRouteStop> sequence) {
        java.util.HashSet<String> pickedUp = new java.util.HashSet<>();
        for (ActiveRouteStop stop : sequence) {
            if (stop.stopType() == ActiveRouteStopType.PICKUP) {
                pickedUp.add(stop.orderId());
            } else if (!pickedUp.contains(stop.orderId())) {
                return false;
            }
        }
        return true;
    }

    private double geometryCost(GeoPoint currentLocation, List<ActiveRouteStop> sequence) {
        double cost = 0.0;
        GeoPoint previous = currentLocation;
        for (ActiveRouteStop stop : sequence) {
            cost += distance(previous, stop.location());
            previous = stop.location();
        }
        return cost;
    }

    private double distance(GeoPoint left, GeoPoint right) {
        if (left == null || right == null) {
            return Double.POSITIVE_INFINITY;
        }
        double lat = left.latitude() - right.latitude();
        double lon = left.longitude() - right.longitude();
        return Math.sqrt(lat * lat + lon * lon);
    }

    private record RepairMove(List<ActiveRouteStop> stopSequence, double cost) {
    }
}
