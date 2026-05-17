package com.routechain.runtime.queue;

public final class QueueRouter {
    public QueueLane route(String profile, String kind) {
        if ("RESCUE".equalsIgnoreCase(kind)) return QueueLane.RESCUE;
        if ("LIVE".equalsIgnoreCase(kind) || "LIVE_ROLLING".equalsIgnoreCase(profile)) return QueueLane.LIVE;
        if ("BENCHMARK".equalsIgnoreCase(kind)) return QueueLane.BENCHMARK;
        if (profile != null && profile.toUpperCase().contains("QUALITY")) return QueueLane.QUALITY;
        return QueueLane.FAST;
    }
    public int priority(QueueLane lane) {
        return switch (lane) { case RESCUE -> 0; case LIVE -> 1; case FAST -> 2; case QUALITY -> 3; case BENCHMARK -> 4; };
    }
}
