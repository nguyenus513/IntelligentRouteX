package com.routechain.api.bigdata;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/bigdata")
public final class BigDataRuntimeController {
    private final BigDataRuntimeService runtime;

    public BigDataRuntimeController(BigDataRuntimeService runtime) {
        this.runtime = runtime;
    }

    @PostMapping("/ingest/{kind}")
    public ResponseEntity<?> ingest(@PathVariable String kind, @RequestBody(required = false) BigDataRuntimeService.IngestRequest request) {
        try {
            return ResponseEntity.accepted().body(ok(runtime.submit(kind, request)));
        } catch (IllegalArgumentException exception) {
            return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", exception.getMessage()));
        } catch (IllegalStateException exception) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).header("Retry-After", "5").body(error("QUEUE_BACKPRESSURE", exception.getMessage()));
        }
    }

    @PostMapping("/ingest/orders")
    public ResponseEntity<?> ingestOrders(@RequestBody(required = false) BigDataRuntimeService.IngestRequest request) {
        return ingest("orders", request);
    }

    @PostMapping("/ingest/drivers")
    public ResponseEntity<?> ingestDrivers(@RequestBody(required = false) BigDataRuntimeService.IngestRequest request) {
        return ingest("drivers", request);
    }

    @PostMapping("/ingest/telemetry")
    public ResponseEntity<?> ingestTelemetry(@RequestBody(required = false) BigDataRuntimeService.IngestRequest request) {
        return ingest("telemetry", request);
    }

    @GetMapping("/jobs/{jobId}")
    public ResponseEntity<?> job(@PathVariable String jobId) {
        return runtime.job(jobId).<ResponseEntity<?>>map(value -> ResponseEntity.ok(ok(value))).orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "job not found")));
    }

    @GetMapping("/jobs/{jobId}/events")
    public ResponseEntity<?> events(@PathVariable String jobId, @RequestParam(defaultValue = "200") int limit) {
        return ResponseEntity.ok(ok(Map.of("items", runtime.events(jobId, limit), "limit", limit)));
    }

    @GetMapping(value = "/jobs/{jobId}/events/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter eventStream(@PathVariable String jobId, @RequestParam(defaultValue = "200") int limit) throws IOException {
        SseEmitter emitter = new SseEmitter(5000L);
        for (Map<String, Object> event : runtime.events(jobId, limit)) emitter.send(SseEmitter.event().name(String.valueOf(event.get("type"))).data(event));
        emitter.complete();
        return emitter;
    }

    @PostMapping("/replay/{jobId}")
    public ResponseEntity<?> replay(@PathVariable String jobId) {
        return runtime.replay(jobId).<ResponseEntity<?>>map(value -> ResponseEntity.accepted().body(ok(value))).orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "source job not found")));
    }

    @GetMapping("/runtime")
    public ResponseEntity<?> runtime() {
        return ResponseEntity.ok(ok(runtime.runtime()));
    }

    @GetMapping("/events")
    public ResponseEntity<?> recentEvents(@RequestParam(defaultValue = "200") int limit) {
        return ResponseEntity.ok(ok(Map.of("items", runtime.recentEvents(limit), "limit", limit)));
    }

    @GetMapping("/lake/summary")
    public ResponseEntity<?> lakeSummary() {
        return ResponseEntity.ok(ok(runtime.lakeSummary()));
    }

    @GetMapping("/openapi-summary")
    public ResponseEntity<?> openApiSummary() {
        return ResponseEntity.ok(ok(Map.of(
                "title", "IRX BigData Dispatch API",
                "version", "v1",
                "style", "OpenAPI-ready REST resources with async jobs and event streams",
                "resources", List.of("ingest", "jobs", "events", "runtime", "lake", "replay", "ai-context"),
                "responseEnvelope", Map.of("ok", "boolean", "requestId", "string", "data", "object", "error", "object|null", "meta", "object")
        )));
    }

    private static Map<String, Object> ok(Object data) {
        return Map.of("ok", true, "requestId", "REQ-" + UUID.randomUUID(), "data", data, "meta", meta());
    }

    private static Map<String, Object> error(String code, String message) {
        return Map.of("ok", false, "requestId", "REQ-" + UUID.randomUUID(), "error", Map.of("code", code, "message", message == null ? "" : message), "meta", meta());
    }

    private static Map<String, Object> meta() {
        return Map.of("version", "v1", "timestamp", Instant.now().toString());
    }
}
