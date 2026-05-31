package com.routechain.v2.bundle;

import com.routechain.domain.Order;
import com.routechain.v2.active.ActiveRouteInsertionCandidate;
import com.routechain.v2.active.ActiveRouteInsertionGenerator;
import com.routechain.v2.active.ActiveRouteState;
import com.routechain.v2.cluster.EtaLegCache;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public final class ConvenientInsertionEngine {
    private final ActiveRouteInsertionGenerator insertionGenerator;

    public ConvenientInsertionEngine() {
        this(new ActiveRouteInsertionGenerator());
    }

    public ConvenientInsertionEngine(ActiveRouteInsertionGenerator insertionGenerator) {
        this.insertionGenerator = insertionGenerator;
    }

    public List<ActiveRouteInsertionCandidate> generate(List<ActiveRouteState> activeRoutes,
                                                        List<BundleCandidate> selectedBundles,
                                                        BundleContext context,
                                                        Instant decisionTime,
                                                        EtaLegCache etaLegCache) {
        List<Order> orders = selectedBundles == null ? List.of() : selectedBundles.stream()
                .flatMap(bundle -> bundle.orderIds().stream())
                .distinct()
                .map(context::order)
                .filter(java.util.Objects::nonNull)
                .toList();
        return generateForOrders(activeRoutes, orders, decisionTime, etaLegCache);
    }

    public List<ActiveRouteInsertionCandidate> generateForOrders(List<ActiveRouteState> activeRoutes,
                                                                 List<Order> orders,
                                                                 Instant decisionTime,
                                                                 EtaLegCache etaLegCache) {
        List<ActiveRouteInsertionCandidate> generated = insertionGenerator.generate(activeRoutes, orders, decisionTime, etaLegCache);
        return generated.stream()
                .filter(ActiveRouteInsertionCandidate::feasible)
                .filter(candidate -> preservesFrozenStop(activeRoutes, candidate))
                .sorted(Comparator.comparingDouble(ActiveRouteInsertionCandidate::score).reversed()
                        .thenComparingDouble(ActiveRouteInsertionCandidate::incrementalCompletionEtaMinutes)
                        .thenComparing(ActiveRouteInsertionCandidate::candidateId))
                .toList();
    }

    public boolean preservesFrozenStop(List<ActiveRouteState> activeRoutes, ActiveRouteInsertionCandidate candidate) {
        ActiveRouteState route = activeRoutes.stream()
                .filter(item -> item.routeId().equals(candidate.routeId()))
                .findFirst()
                .orElse(null);
        if (route == null || route.remainingStopOrder().isEmpty() || candidate.newStopOrder().isEmpty()) {
            return true;
        }
        return route.remainingStopOrder().getFirst().equals(candidate.newStopOrder().getFirst());
    }
}
