package com.routechain.api.bigdata;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/ai")
public final class BigDataAiContextController {
    private final BigDataRuntimeService runtime;

    public BigDataAiContextController(BigDataRuntimeService runtime) {
        this.runtime = runtime;
    }

    @GetMapping("/context/live-summary")
    public ResponseEntity<?> liveSummary() {
        return ResponseEntity.ok(ok(runtime.liveAiContext()));
    }

    @GetMapping("/context/hot-zones")
    public ResponseEntity<?> hotZones() {
        return ResponseEntity.ok(ok(Map.of("items", runtime.hotZones(), "source", "bigdata-runtime-lake-and-queue")));
    }

    @GetMapping("/context/driver-load")
    public ResponseEntity<?> driverLoad() {
        return ResponseEntity.ok(ok(Map.of("items", runtime.driverLoad(), "source", "telemetry-and-driver-events")));
    }

    @GetMapping("/context/late-risk")
    public ResponseEntity<?> lateRisk() {
        return ResponseEntity.ok(ok(Map.of("items", runtime.lateRisk(), "source", "orders-deadline-distance-waiting-context")));
    }

    @PostMapping("/ask")
    public ResponseEntity<?> ask(@RequestBody(required = false) Map<String, Object> request) {
        String question = request == null ? "" : String.valueOf(request.getOrDefault("question", ""));
        Map<String, Object> context = runtime.liveAiContext();
        return ResponseEntity.ok(ok(Map.of(
                "mode", "CONTEXT_ONLY_ASSISTANT_STUB",
                "question", question,
                "answer", answer(question, context),
                "context", context,
                "guardrail", "AI may notify/recommend only; IRX solver remains authoritative."
        )));
    }

    @PostMapping("/notify/analyze")
    public ResponseEntity<?> notifyAnalyze() {
        return ResponseEntity.ok(ok(Map.of(
                "notifications", List.of(
                        Map.of("level", "info", "type", "HOT_ZONE", "message", "Review hot-zone context before adding drivers", "data", runtime.hotZones()),
                        Map.of("level", "warn", "type", "LATE_RISK", "message", "Orders with high late risk need dispatch priority", "data", runtime.lateRisk()),
                        Map.of("level", "info", "type", "DRIVER_LOAD", "message", "Driver workload balance snapshot", "data", runtime.driverLoad())
                ),
                "contextSource", "backend-bigdata-runtime"
        )));
    }

    private static String answer(String question, Map<String, Object> context) {
        String normalized = question == null ? "" : question.toLowerCase();
        if (normalized.contains("khu") || normalized.contains("zone") || normalized.contains("nổ")) return "Hot-zone context is attached in data.demand.hotZones; prioritize driver supply near HIGH risk zones.";
        if (normalized.contains("driver") || normalized.contains("tài")) return "Driver workload context is attached in data.driverLoad; overloaded drivers should receive fewer new insertions.";
        if (normalized.contains("late") || normalized.contains("trễ")) return "Late-risk orders are attached in data.lateRisk; use ETA, distance, waiting time, and deadline as the decision context.";
        return context.isEmpty() ? "insufficient_context" : "Use the attached structured context; no route mutation is performed by AI.";
    }

    private static Map<String, Object> ok(Object data) {
        return Map.of("ok", true, "requestId", "REQ-" + UUID.randomUUID(), "data", data, "meta", Map.of("version", "v1", "timestamp", Instant.now().toString()));
    }
}
