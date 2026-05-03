package com.routechain.v2.constraints;

import java.util.Map;

public record ConstraintViolation(
        String code,
        String detail,
        String severity,
        String entityType,
        String entityId,
        String candidateId,
        Map<String, Object> evidence) {

    public ConstraintViolation {
        code = code == null || code.isBlank() ? "unknown-constraint-violation" : code;
        detail = detail == null ? "" : detail;
        severity = severity == null || severity.isBlank() ? "HARD" : severity;
        entityType = entityType == null ? "candidate" : entityType;
        entityId = entityId == null ? "" : entityId;
        candidateId = candidateId == null ? entityId : candidateId;
        evidence = evidence == null ? Map.of() : Map.copyOf(evidence);
    }

    public ConstraintViolation(String code, String detail) {
        this(code, detail, "HARD", "candidate", detail, detail, Map.of());
    }

    public static ConstraintViolation candidate(String code, String candidateId, String detail) {
        return new ConstraintViolation(code, detail, "HARD", "candidate", candidateId, candidateId, Map.of());
    }

    public static ConstraintViolation withEvidence(String code, String candidateId, String detail, Map<String, Object> evidence) {
        return new ConstraintViolation(code, detail, "HARD", "candidate", candidateId, candidateId, evidence);
    }
}
