package com.routefood.app.data.model;

public class RecommendationItem {
    private final String id;
    private final String type;
    private final String targetId;
    private final double score;
    private final String reason;

    public RecommendationItem(String id, String type, String targetId, double score, String reason) {
        this.id = id;
        this.type = type;
        this.targetId = targetId;
        this.score = score;
        this.reason = reason;
    }

    public String id() {
        return id;
    }

    public String type() {
        return type;
    }

    public String targetId() {
        return targetId;
    }

    public double score() {
        return score;
    }

    public String reason() {
        return reason;
    }
}
