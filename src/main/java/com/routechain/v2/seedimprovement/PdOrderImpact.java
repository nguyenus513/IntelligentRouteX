package com.routechain.v2.seedimprovement;

public record PdOrderImpact(
        String orderId,
        String routeId,
        double detourContributionKm,
        double spreadKm,
        double routeDistancePerOrderKm,
        double score) {
}
