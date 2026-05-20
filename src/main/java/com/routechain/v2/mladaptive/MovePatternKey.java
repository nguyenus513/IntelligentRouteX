package com.routechain.v2.mladaptive;

public record MovePatternKey(
        String operatorType,
        String seedSource,
        String routeSizeBucket,
        String slackBucket,
        String loadBucket,
        String distanceBucket) {

    public static MovePatternKey from(String operatorType, String seedSource, double improvementKm) {
        return new MovePatternKey(
                safe(operatorType),
                safe(seedSource),
                "unknown-route-size",
                "unknown-slack",
                "unknown-load",
                improvementKm >= 1.0 ? "large-gain" : improvementKm > 0.0 ? "small-gain" : "no-gain");
    }

    public String key() {
        return operatorType + "|" + seedSource + "|" + routeSizeBucket + "|" + slackBucket + "|" + loadBucket + "|" + distanceBucket;
    }

    private static String safe(String value) {
        return value == null || value.isBlank() ? "UNKNOWN" : value;
    }
}
