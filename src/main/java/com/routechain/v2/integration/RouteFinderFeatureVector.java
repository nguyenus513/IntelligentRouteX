package com.routechain.v2.integration;

import java.util.List;

public record RouteFinderFeatureVector(
        String schemaVersion,
        String traceId,
        String bundleId,
        String anchorOrderId,
        String driverId,
        String baselineSource,
        List<String> baselineStopOrder,
        List<String> bundleOrderIds,
        double projectedPickupEtaMinutes,
        double projectedCompletionEtaMinutes,
        double rerankScore,
        double bundleScore,
        double anchorScore,
        double averagePairSupport,
        boolean boundaryCross,
        int maxAlternatives,
        List<RouteFinderNode> vrpNodes,
        double vehicleCapacity) {

    public RouteFinderFeatureVector(String schemaVersion,
                                    String traceId,
                                    String bundleId,
                                    String anchorOrderId,
                                    String driverId,
                                    String baselineSource,
                                    List<String> baselineStopOrder,
                                    List<String> bundleOrderIds,
                                    double projectedPickupEtaMinutes,
                                    double projectedCompletionEtaMinutes,
                                    double rerankScore,
                                    double bundleScore,
                                    double anchorScore,
                                    double averagePairSupport,
                                    boolean boundaryCross,
                                    int maxAlternatives) {
        this(schemaVersion, traceId, bundleId, anchorOrderId, driverId, baselineSource, baselineStopOrder, bundleOrderIds,
                projectedPickupEtaMinutes, projectedCompletionEtaMinutes, rerankScore, bundleScore, anchorScore,
                averagePairSupport, boundaryCross, maxAlternatives, List.of(), 1.0);
    }

    public RouteFinderFeatureVector {
        baselineStopOrder = baselineStopOrder == null ? List.of() : List.copyOf(baselineStopOrder);
        bundleOrderIds = bundleOrderIds == null ? List.of() : List.copyOf(bundleOrderIds);
        vrpNodes = vrpNodes == null ? List.of() : List.copyOf(vrpNodes);
        vehicleCapacity = vehicleCapacity <= 0.0 ? 1.0 : vehicleCapacity;
    }

    public record RouteFinderNode(
            String nodeId,
            String orderId,
            String nodeType,
            double latitude,
            double longitude,
            double demand,
            double readyTimeMinutes,
            double dueTimeMinutes,
            double serviceTimeMinutes) {
    }
}
