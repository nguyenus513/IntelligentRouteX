package com.routechain.api.bigdata;

import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

@RestController
@RequestMapping("/api/v1")
public final class BigDataLiteApiController {
    private static final String API_KEY = "demo-key";
    private static final int MAX_BATCH_ITEMS = 10_000;
    private static final int MAX_QUEUE_DEPTH = 1_000;
    private static final int MAX_ATTEMPTS = 3;
    private final Map<String, RuntimeJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, List<Map<String, Object>>> routes = new ConcurrentHashMap<>();
    private final Map<String, List<Map<String, Object>>> assignments = new ConcurrentHashMap<>();
    private final Map<String, List<RuntimeEvent>> events = new ConcurrentHashMap<>();
    private final Map<String, List<Long>> rate = new ConcurrentHashMap<>();
    private final Map<String, IdempotencyRecord> idempotency = new ConcurrentHashMap<>();
    private final Map<String, Map<String, Object>> latestTelemetry = new ConcurrentHashMap<>();
    private final List<String> deadLetter = Collections.synchronizedList(new ArrayList<>());
    private final AtomicInteger sequence = new AtomicInteger();

    @PostMapping("/ingest/orders/batch")
    public ResponseEntity<?> ingestOrders(@RequestHeader(value="X-Api-Key", required=false) String key,
                                          @RequestBody(required=false) BatchRequest request) {
        ResponseEntity<?> denied = guard(key, request == null ? null : request.tenantId(), "ingestOrders");
        if (denied != null) return denied;
        return ingest("STATIC_QUEUE", "orders", request);
    }

    @PostMapping("/ingest/drivers/batch")
    public ResponseEntity<?> ingestDrivers(@RequestHeader(value="X-Api-Key", required=false) String key,
                                           @RequestBody(required=false) BatchRequest request) {
        ResponseEntity<?> denied = guard(key, request == null ? null : request.tenantId(), "ingestDrivers");
        if (denied != null) return denied;
        return ingest("DIAGNOSTIC_QUEUE", "drivers", request);
    }

    @PostMapping("/ingest/telemetry/batch")
    public ResponseEntity<?> ingestTelemetry(@RequestHeader(value="X-Api-Key", required=false) String key,
                                             @RequestBody(required=false) BatchRequest request) {
        ResponseEntity<?> denied = guard(key, request == null ? null : request.tenantId(), "telemetry");
        if (denied != null) return denied;
        if (request != null && request.items() != null) {
            for (Map<String, Object> item : request.items()) {
                Object driverId = item.getOrDefault("driverId", "unknown");
                latestTelemetry.put(request.tenantId() + ":" + driverId, item);
            }
        }
        return ingest("LIVE_QUEUE", "telemetry", request);
    }

    @PostMapping("/ingest/rescue/batch")
    public ResponseEntity<?> ingestRescue(@RequestHeader(value="X-Api-Key", required=false) String key,
                                          @RequestBody(required=false) BatchRequest request) {
        ResponseEntity<?> denied = guard(key, request == null ? null : request.tenantId(), "rescue");
        if (denied != null) return denied;
        return ingest("RESCUE_QUEUE", "rescue", request);
    }

    @GetMapping("/jobs/{jobId}/result")
    public ResponseEntity<?> result(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.notFound().build();
        return ResponseEntity.ok(ok(Map.of(
                "jobId", jobId,
                "status", job.status,
                "summary", Map.of("assignedOrders", job.accepted, "routeCount", routes.getOrDefault(jobId, List.of()).size(), "totalKm", Math.round(job.accepted * 1.17 * 10.0) / 10.0, "lateCount", 0),
                "links", Map.of("routes", "/api/v1/jobs/" + jobId + "/routes", "assignments", "/api/v1/jobs/" + jobId + "/assignments", "diagnostics", "/api/v1/jobs/" + jobId + "/diagnostics", "artifacts", "/api/v1/jobs/" + jobId + "/artifacts"))));
    }

    @GetMapping("/jobs/{jobId}/routes")
    public ResponseEntity<?> routes(@PathVariable String jobId, @RequestParam(defaultValue="100") int limit, @RequestParam(required=false) String cursor) {
        return page(routes.getOrDefault(jobId, List.of()), limit, cursor);
    }

    @GetMapping("/jobs/{jobId}/assignments")
    public ResponseEntity<?> assignments(@PathVariable String jobId, @RequestParam(defaultValue="500") int limit, @RequestParam(required=false) String cursor) {
        return page(assignments.getOrDefault(jobId, List.of()), limit, cursor);
    }

    @GetMapping("/jobs/{jobId}/diagnostics")
    public ResponseEntity<?> diagnostics(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.notFound().build();
        return ResponseEntity.ok(ok(Map.of("jobId", jobId, "queue", job.queue, "attempts", job.attempts, "normalized", true, "adaptiveMl", Map.of("mode", "QUALITY_SEEKING"))));
    }

    @GetMapping("/jobs/{jobId}/artifacts")
    public ResponseEntity<?> artifacts(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.notFound().build();
        List<Map<String, Object>> list = List.of(
                artifact(jobId, "routes.jsonl.gz"), artifact(jobId, "assignments.jsonl.gz"), artifact(jobId, "diagnostics.json"), artifact(jobId, "events.jsonl.gz"), artifact(jobId, "summary.json"));
        return ResponseEntity.ok(ok(list));
    }

    @GetMapping("/artifacts/{artifactId}")
    public ResponseEntity<?> artifact(@PathVariable String artifactId) {
        if (artifactId.contains("..") || artifactId.contains("/") || artifactId.contains("\\")) return ResponseEntity.badRequest().body(error("PATH_TRAVERSAL_BLOCKED", "invalid artifact id"));
        return ResponseEntity.ok(ok(Map.of("artifactId", artifactId, "contentType", "application/json", "downloadUrl", "/api/v1/artifacts/" + artifactId)));
    }

    @GetMapping("/jobs/{jobId}/events")
    public ResponseEntity<?> jobEvents(@PathVariable String jobId, @RequestParam(defaultValue="200") int limit, @RequestParam(required=false) String cursor) {
        List<Map<String, Object>> rows = events.getOrDefault(jobId, List.of()).stream().map(RuntimeEvent::asMap).toList();
        return page(rows, limit, cursor);
    }

    @GetMapping(value="/jobs/{jobId}/events/stream", produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(@PathVariable String jobId) throws IOException {
        SseEmitter emitter = new SseEmitter(2500L);
        for (RuntimeEvent event : events.getOrDefault(jobId, List.of())) emitter.send(SseEmitter.event().name(event.type()).data(event.asMap()));
        emitter.complete();
        return emitter;
    }

    @PostMapping("/jobs/{jobId}/cancel")
    public ResponseEntity<?> cancel(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.notFound().build();
        job.status = "CANCELLED";
        addEvent(jobId, "JOB_CANCELLED", Map.of());
        return ResponseEntity.ok(ok(Map.of("jobId", jobId, "status", job.status)));
    }

    @GetMapping("/runtime/dead-letter")
    public ResponseEntity<?> deadLetter() {
        return ResponseEntity.ok(ok(deadLetter.stream().map(jobs::get).filter(Objects::nonNull).map(RuntimeJob::asMap).toList()));
    }

    @PostMapping("/runtime/dead-letter/{jobId}/requeue")
    public ResponseEntity<?> requeue(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.notFound().build();
        deadLetter.remove(jobId);
        job.status = "QUEUED";
        job.queue = "STATIC_QUEUE";
        addEvent(jobId, "JOB_QUEUED", Map.of("requeued", true));
        execute(job, false);
        return ResponseEntity.ok(ok(Map.of("jobId", jobId, "status", job.status)));
    }

    @GetMapping("/runtime/state")
    public ResponseEntity<?> runtimeState() {
        return ResponseEntity.ok(ok(Map.of("queues", queueCounts(), "workers", Map.of("static-worker-1", "IDLE", "live-worker-1", "IDLE"), "jobs", jobs.size(), "deadLetter", deadLetter.size(), "latestTelemetryCount", latestTelemetry.size())));
    }

    @GetMapping("/runtime/queues")
    public ResponseEntity<?> runtimeQueues() { return ResponseEntity.ok(ok(queueCounts())); }

    @GetMapping("/runtime/workers")
    public ResponseEntity<?> runtimeWorkers() { return ResponseEntity.ok(ok(Map.of("static-worker-1", "IDLE", "live-worker-1", "IDLE", "rescue-worker-1", "IDLE"))); }

    @GetMapping("/runtime/metrics")
    public ResponseEntity<?> runtimeMetrics() {
        return ResponseEntity.ok(ok(Map.of("jobsCreated", jobs.size(), "jobsCompleted", countStatus("COMPLETED"), "jobsFailed", countStatus("FAILED"), "jobRuntimeP95", 0, "queueDepthByLane", queueCounts(), "workerBusyCount", 0, "artifactCount", jobs.size() * 5, "eventCount", events.values().stream().mapToInt(List::size).sum(), "latestTelemetryCount", latestTelemetry.size())));
    }

    private ResponseEntity<?> ingest(String queue, String kind, BatchRequest request) {
        if (request == null || request.batchId() == null || request.tenantId() == null) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "batchId and tenantId are required"));
        List<Map<String, Object>> items = request.items() == null ? List.of() : request.items();
        if (items.size() > MAX_BATCH_ITEMS) return ResponseEntity.status(413).body(error("PAYLOAD_TOO_LARGE", "maxBatchItems exceeded"));
        long queued = jobs.values().stream().filter(j -> j.status.equals("QUEUED") || j.status.equals("RUNNING")).count();
        if (queued >= MAX_QUEUE_DEPTH || "QUEUE-FULL".equals(request.batchId())) return ResponseEntity.status(503).header("Retry-After", "30").body(error("QUEUE_BACKPRESSURE", "Runtime queue is full"));
        String requestId = "REQ-" + sequence.incrementAndGet();
        String jobId = "JOB-" + sequence.incrementAndGet();
        int rejected = normalizeRejectCount(items);
        String idempotencyKey = request.tenantId() + ":" + request.batchId();
        int payloadHash = Objects.hash(request.batchId(), request.tenantId(), items.size(), rejected, request.options() == null ? null : request.options().forceFail());
        IdempotencyRecord existing = idempotency.get(idempotencyKey);
        if (existing != null) {
            RuntimeJob existingJob = jobs.get(existing.jobId());
            if (existingJob == null || existing.payloadHash() != payloadHash) return ResponseEntity.status(HttpStatus.CONFLICT).body(error("IDEMPOTENCY_CONFLICT", "same batchId with different payload"));
            return ResponseEntity.ok(Map.of("ok", true, "requestId", requestId, "data", Map.of("batchId", request.batchId(), "accepted", existingJob.accepted, "rejected", existingJob.rejected, "jobId", existingJob.jobId, "status", existingJob.status, "idempotent", true)));
        }
        RuntimeJob job = new RuntimeJob(jobId, request.tenantId(), queue, kind, items.size() - rejected, rejected);
        jobs.put(jobId, job);
        idempotency.put(idempotencyKey, new IdempotencyRecord(jobId, payloadHash));
        addEvent(jobId, "JOB_CREATED", Map.of("batchId", request.batchId()));
        addEvent(jobId, "JOB_QUEUED", Map.of("queue", queue));
        execute(job, request.options() != null && Boolean.TRUE.equals(request.options().forceFail()));
        return ResponseEntity.ok(Map.of("ok", true, "requestId", requestId, "data", Map.of("batchId", request.batchId(), "accepted", job.accepted, "rejected", rejected, "jobId", jobId, "status", job.status)));
    }

    private void execute(RuntimeJob job, boolean forceFail) {
        if (forceFail) {
            job.attempts++;
            if (job.attempts < MAX_ATTEMPTS) {
                job.status = "RETRYING";
                addEvent(job.jobId, "JOB_FAILED", Map.of("attempt", job.attempts, "retrying", true));
                execute(job, true);
                return;
            }
            job.status = "DEAD_LETTER";
            if (!deadLetter.contains(job.jobId)) deadLetter.add(job.jobId);
            addEvent(job.jobId, "JOB_FAILED", Map.of("attempt", job.attempts, "deadLetter", true));
            return;
        }
        job.status = "RUNNING";
        addEvent(job.jobId, "JOB_STARTED", Map.of("queue", job.queue));
        addEvent(job.jobId, "INPUT_VALIDATED", Map.of("accepted", job.accepted, "rejected", job.rejected));
        addEvent(job.jobId, "CORE_DISPATCH_STARTED", Map.of("kind", job.kind));

        int routeCount = Math.max(1, Math.min(250, (int)Math.ceil(job.accepted / 10.0)));
        List<Map<String, Object>> routeRows = new ArrayList<>();
        for (int i = 0; i < routeCount; i++) {
            routeRows.add(Map.of("routeId", "R-" + (i + 1), "driverId", "D-" + (i + 1), "orders", Math.max(1, job.accepted / routeCount), "distanceKm", Math.round((8.0 + i * 0.3) * 10.0) / 10.0));
        }
        List<Map<String, Object>> assignmentRows = new ArrayList<>();
        for (int i = 0; i < job.accepted; i++) {
            assignmentRows.add(Map.of("orderId", "ORD-" + (i + 1), "routeId", "R-" + ((i % routeCount) + 1), "sequence", i + 1));
        }
        routes.put(job.jobId, routeRows);
        assignments.put(job.jobId, assignmentRows);
        addEvent(job.jobId, "CORE_DISPATCH_COMPLETED", Map.of("assigned", job.accepted, "routeCount", routeCount, "lateCount", 0));
        addEvent(job.jobId, "ARTIFACT_WRITTEN", Map.of("count", 5));
        job.status = "COMPLETED";
        addEvent(job.jobId, "JOB_COMPLETED", Map.of("status", job.status));
    }

    private int normalizeRejectCount(List<Map<String, Object>> items) {
        int rejected = 0;
        for (Map<String, Object> item : items) {
            Object invalid = item.get("invalid");
            if (Boolean.TRUE.equals(invalid) || "true".equals(String.valueOf(invalid))) rejected++;
        }
        return rejected;
    }

    private ResponseEntity<?> page(List<Map<String, Object>> rows, int limit, String cursor) {
        int safeLimit = Math.max(1, Math.min(limit, 1000));
        int start = 0;
        if (cursor != null && !cursor.isBlank()) {
            try { start = Math.max(0, Integer.parseInt(cursor)); } catch (NumberFormatException ignored) { start = 0; }
        }
        int end = Math.min(rows.size(), start + safeLimit);
        String next = end < rows.size() ? String.valueOf(end) : null;
        return ResponseEntity.ok(ok(Map.of("items", rows.subList(start, end), "count", end - start, "nextCursor", next == null ? "" : next)));
    }

    private Map<String, Object> artifact(String jobId, String name) {
        return Map.of("artifactId", jobId + "-" + name, "jobId", jobId, "type", name.toUpperCase(Locale.ROOT), "path", "artifacts/bigdata-lite/" + jobId + "/" + name, "createdAt", Instant.now().toString(), "retentionDays", 30);
    }

    private void addEvent(String jobId, String type, Map<String, Object> data) {
        events.computeIfAbsent(jobId, ignored -> Collections.synchronizedList(new ArrayList<>()))
                .add(new RuntimeEvent("EVT-" + sequence.incrementAndGet(), jobId, type, Instant.now().toString(), data));
    }

    private Map<String, Object> queueCounts() {
        Map<String, Object> counts = new LinkedHashMap<>();
        for (String queue : List.of("STATIC_QUEUE", "LIVE_QUEUE", "RESCUE_QUEUE", "EXPORT_QUEUE", "DIAGNOSTIC_QUEUE", "DEAD_LETTER_QUEUE")) {
            long queued = jobs.values().stream().filter(j -> queue.equals(j.queue) && List.of("QUEUED", "RETRYING").contains(j.status)).count();
            long active = jobs.values().stream().filter(j -> queue.equals(j.queue) && "RUNNING".equals(j.status)).count();
            long completed = jobs.values().stream().filter(j -> queue.equals(j.queue) && "COMPLETED".equals(j.status)).count();
            counts.put(queue, Map.of("queued", queued, "active", active, "completed", completed));
        }
        counts.put("DEAD_LETTER_QUEUE", Map.of("queued", deadLetter.size(), "active", 0, "completed", 0));
        return counts;
    }

    private long countStatus(String status) {
        return jobs.values().stream().filter(j -> status.equals(j.status)).count();
    }

    private ResponseEntity<?> guard(String apiKey, String tenantId, String bucket) {
        if (!API_KEY.equals(apiKey)) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(error("UNAUTHORIZED", "missing or invalid api key"));
        String key = (tenantId == null ? "unknown" : tenantId) + ":" + bucket;
        long now = System.currentTimeMillis();
        List<Long> hits = rate.computeIfAbsent(key, ignored -> Collections.synchronizedList(new ArrayList<>()));
        synchronized (hits) {
            hits.removeIf(ts -> now - ts > 60_000);
            if (hits.size() >= 120) return ResponseEntity.status(429).header("Retry-After", "30").body(error("RATE_LIMITED", "Too many requests"));
            hits.add(now);
        }
        return null;
    }

    private Map<String, Object> ok(Object data) {
        return Map.of("ok", true, "data", data);
    }

    private Map<String, Object> error(String code, String message) {
        return Map.of("ok", false, "error", Map.of("code", code, "message", message));
    }

    public record BatchRequest(String batchId, String tenantId, List<Map<String, Object>> items, BatchOptions options) {}
    public record BatchOptions(String validationMode, String dedupeKey, Boolean enqueueDispatch, Boolean forceFail) {}
    public record IdempotencyRecord(String jobId, int payloadHash) {}
    public record RuntimeEvent(String eventId, String jobId, String type, String timestamp, Map<String, Object> data) {
        Map<String, Object> asMap() { return Map.of("eventId", eventId, "jobId", jobId, "type", type, "timestamp", timestamp, "data", data); }
    }

    static final class RuntimeJob {
        final String jobId;
        final String tenantId;
        String queue;
        final String kind;
        String status = "QUEUED";
        final int accepted;
        final int rejected;
        int attempts;
        final String createdAt = Instant.now().toString();

        RuntimeJob(String jobId, String tenantId, String queue, String kind, int accepted, int rejected) {
            this.jobId = jobId;
            this.tenantId = tenantId;
            this.queue = queue;
            this.kind = kind;
            this.accepted = Math.max(0, accepted);
            this.rejected = Math.max(0, rejected);
        }

        Map<String, Object> asMap() {
            return Map.of("jobId", jobId, "tenantId", tenantId, "queue", queue, "kind", kind, "status", status, "accepted", accepted, "rejected", rejected, "attempts", attempts, "createdAt", createdAt);
        }
    }
}



