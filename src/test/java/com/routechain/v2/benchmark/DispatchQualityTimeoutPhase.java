package com.routechain.v2.benchmark;

public enum DispatchQualityTimeoutPhase {
    NONE("none"),
    DISPATCH_TIMEOUT("dispatch-timeout"),
    ARTIFACT_WRITE_TIMEOUT("artifact-write-timeout"),
    TASK_LOCK_TIMEOUT("task-lock-timeout"),
    UNKNOWN_TIMEOUT("unknown-timeout");

    private final String wireName;

    DispatchQualityTimeoutPhase(String wireName) {
        this.wireName = wireName;
    }

    public String wireName() {
        return wireName;
    }
}
