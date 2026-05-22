package com.routechain.api.bigdata;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

@Service
public final class BigDataRuntimeService {
    private static final int MAX_BATCH_ITEMS = 10_000;
    private static final int MAX_QUEUE_DEPTH = 1_000;
    private static final int MAX_EVENT_BUFFER = 2_000;
    private static final int MAX_JOB_EVENTS = 500;
    private static final int WORKERS = 2;

    private final ObjectMapper objectMapper;
    private final Map<String, RuntimeJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, Deque<RuntimeEvent>> jobEvents = new ConcurrentHashMap<>();
    private final Deque<RuntimeEvent> recentEvents = new ConcurrentLinkedDeque<>();
    private final BlockingQueue<String> queue = new LinkedBlockingQueue<>();
    private final AtomicLong sequence = new AtomicLong();
    private final AtomicLong completedJobs = new AtomicLong();
    private final AtomicLong failedJobs = new AtomicLong();
    private final AtomicLong deadLetterJobs = new AtomicLong();
    private final AtomicLong lakeBytesWritten = new AtomicLong();
    private final AtomicLong lakeRowsWritten = new AtomicLong();
    private final AtomicLong totalLatencyMs = new AtomicLong();
    private final AtomicInteger activeWorkers = new AtomicInteger();
    private final ExecutorService executor = Executors.newFixedThreadPool(WORKERS);
    private volatile boolean running;

    public BigDataRuntimeService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @PostConstruct
    void start() {
        running = true;
        for (int i = 0; i < WORKERS; i++) executor.submit(this::workerLoop);
    }

    @PreDestroy
    void stop() {
        running = false;
        executor.shutdownNow();
    }

    public SubmitResult submit(String kind, IngestRequest request) {
        if (request == null || blank(request.batchId()) || blank(request.tenantId())) {
            throw new IllegalArgumentException("batchId and tenantId are required");
        }
        List<Map<String, Object>> items = request.items() == null ? List.of() : request.items();
        if (items.size() > MAX_BATCH_ITEMS) throw new IllegalArgumentException("maxBatchItems exceeded");
        if (queue.size() >= MAX_QUEUE_DEPTH) throw new IllegalStateException("Runtime queue is full");
        String normalizedKind = normalizeKind(kind);
        String lane = laneFor(normalizedKind);
        String jobId = "BDJ-" + sequence.incrementAndGet() + "-" + UUID.randomUUID().toString().substring(0, 8);
        int rejected = rejectCount(items);
        RuntimeJob job = new RuntimeJob(jobId, request.batchId(), request.tenantId(), normalizedKind, lane, items, items.size() - rejected, rejected, forceFail(request), Instant.now().toString());
        jobs.put(jobId, job);
        event(jobId, "INGEST_ACCEPTED", Map.of("kind", normalizedKind, "lane", lane, "items", items.size(), "accepted", job.accepted, "rejected", rejected));
        event(jobId, "NORMALIZED", Map.of("schema", "irx-bigdata-event/v1", "dedupeKey", request.options() == null ? "batchId" : String.valueOf(request.options().getOrDefault("dedupeKey", "batchId"))));
        queue.offer(jobId);
        event(jobId, "QUEUED", Map.of("queueDepth", queue.size(), "maxQueueDepth", MAX_QUEUE_DEPTH));
        return new SubmitResult(jobId, job.batchId, job.tenantId, job.kind, job.lane, job.status, job.accepted, job.rejected, queue.size(), links(jobId));
    }

    public Optional<Map<String, Object>> job(String jobId) {
        RuntimeJob job = jobs.get(jobId);
        return job == null ? Optional.empty() : Optional.of(jobView(job));
    }

    public List<Map<String, Object>> events(String jobId, int limit) {
        Deque<RuntimeEvent> rows = jobEvents.getOrDefault(jobId, new ConcurrentLinkedDeque<>());
        return tail(rows, limit).stream().map(RuntimeEvent::asMap).toList();
    }

    public List<Map<String, Object>> recentEvents(int limit) {
        return tail(recentEvents, limit).stream().map(RuntimeEvent::asMap).toList();
    }

    public Optional<SubmitResult> replay(String jobId) {
        RuntimeJob source = jobs.get(jobId);
        if (source == null) return Optional.empty();
        IngestRequest request = new IngestRequest("replay-" + source.batchId + "-" + sequence.incrementAndGet(), source.tenantId, source.items, Map.of("replayOf", jobId));
        SubmitResult result = submit(source.kind, request);
        event(result.jobId(), "REPLAY_CREATED", Map.of("sourceJobId", jobId));
        return Optional.of(result);
    }

    public Map<String, Object> runtime() {
        long completed = completedJobs.get();
        long total = jobs.size();
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schemaVersion", "irx-bigdata-runtime/v1");
        payload.put("mode", "INTERNAL_ASYNC_QUEUE_WITH_FILE_LAKE");
        payload.put("queueDepth", queue.size());
        payload.put("maxQueueDepth", MAX_QUEUE_DEPTH);
        payload.put("activeWorkers", activeWorkers.get());
        payload.put("workerCount", WORKERS);
        payload.put("jobsCreated", total);
        payload.put("jobsCompleted", completed);
        payload.put("jobsFailed", failedJobs.get());
        payload.put("deadLetter", deadLetterJobs.get());
        payload.put("avgLatencyMs", completed == 0 ? 0 : totalLatencyMs.get() / completed);
        payload.put("lake", lakeSummary());
        payload.put("lanes", laneSummary());
        payload.put("uiPolicy", Map.of("eventWindow", MAX_EVENT_BUFFER, "recommendedPollMs", 750, "renderTopN", 200, "autoScrollDefault", false));
        return payload;
    }

    public Map<String, Object> lakeSummary() {
        return Map.of(
                "schemaVersion", "irx-file-lake-summary/v1",
                "baseDir", "data/irx-lake",
                "format", "JSONL",
                "partitioning", "dataset/dt=YYYY-MM-DD/tenant=<tenant>/part-00000.jsonl",
                "rowsWritten", lakeRowsWritten.get(),
                "bytesWritten", lakeBytesWritten.get(),
                "datasets", List.of("orders", "drivers", "telemetry", "dispatch-results", "events")
        );
    }

    public Map<String, Object> liveAiContext() {
        List<RuntimeJob> latest = jobs.values().stream().sorted((a, b) -> b.createdAt.compareTo(a.createdAt)).limit(20).toList();
        long buffered = latest.stream().filter(job -> List.of("QUEUED", "RUNNING").contains(job.status)).mapToLong(job -> job.accepted).sum();
        long completed = latest.stream().filter(job -> "COMPLETED".equals(job.status)).mapToLong(job -> job.accepted).sum();
        return Map.of(
                "schemaVersion", "irx-ai-live-context/v1",
                "generatedAt", Instant.now().toString(),
                "runtime", runtime(),
                "demand", Map.of("bufferedOrders", buffered, "recentCompletedOrders", completed, "hotZones", hotZones()),
                "driverLoad", driverLoad(),
                "lateRisk", lateRisk(),
                "instructions", "Answer only from this context. If evidence is missing, return insufficient_context. AI may recommend, not mutate dispatch routes."
        );
    }

    public List<Map<String, Object>> hotZones() {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (RuntimeJob job : jobs.values()) {
            for (Map<String, Object> item : job.items) {
                String zone = String.valueOf(item.getOrDefault("zone", item.getOrDefault("district", zoneFromLatLng(item))));
                counts.merge(zone, 1, Integer::sum);
            }
        }
        return counts.entrySet().stream()
                .sorted((left, right) -> Integer.compare(right.getValue(), left.getValue()))
                .limit(8)
                .map(entry -> Map.<String, Object>of("zone", entry.getKey(), "orders", entry.getValue(), "risk", entry.getValue() >= 20 ? "HIGH" : entry.getValue() >= 8 ? "MEDIUM" : "LOW"))
                .toList();
    }

    public List<Map<String, Object>> driverLoad() {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (RuntimeJob job : jobs.values()) {
            for (Map<String, Object> item : job.items) {
                Object driverId = item.get("driverId");
                if (driverId != null) counts.merge(String.valueOf(driverId), 1, Integer::sum);
            }
        }
        return counts.entrySet().stream()
                .sorted((left, right) -> Integer.compare(right.getValue(), left.getValue()))
                .limit(10)
                .map(entry -> Map.<String, Object>of("driverId", entry.getKey(), "events", entry.getValue(), "load", entry.getValue() >= 30 ? "OVERLOADED" : entry.getValue() >= 12 ? "BUSY" : "NORMAL"))
                .toList();
    }

    public List<Map<String, Object>> lateRisk() {
        List<Map<String, Object>> risks = new ArrayList<>();
        for (RuntimeJob job : jobs.values()) {
            for (Map<String, Object> item : job.items) {
                Object orderId = item.get("orderId");
                if (orderId == null) continue;
                double deadline = number(item.get("deadlineMinutes"), 60.0);
                double age = number(item.get("waitingMinutes"), 0.0);
                double distance = number(item.get("distanceKm"), 4.0);
                double score = Math.min(100.0, age * 5.0 + distance * 3.0 + Math.max(0.0, 45.0 - deadline));
                if (score >= 35.0) risks.add(Map.of("orderId", orderId, "riskScore", Math.round(score), "reason", "deadline/distance/waiting-time"));
            }
        }
        return risks.stream().limit(12).toList();
    }

    private void workerLoop() {
        while (running) {
            try {
                String jobId = queue.poll(500, TimeUnit.MILLISECONDS);
                if (jobId == null) continue;
                RuntimeJob job = jobs.get(jobId);
                if (job == null || "CANCELLED".equals(job.status)) continue;
                process(job);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private void process(RuntimeJob job) {
        long started = System.currentTimeMillis();
        activeWorkers.incrementAndGet();
        try {
            job.status = "RUNNING";
            job.startedAt = Instant.now().toString();
            event(job.jobId, "DISPATCH_STARTED", Map.of("lane", job.lane, "accepted", job.accepted));
            if (job.forceFail) throw new IllegalStateException("forced failure for DLQ demo");
            writeLake(job.kind, job.tenantId, job.items);
            int routeCount = Math.max(1, Math.min(250, (int) Math.ceil(job.accepted / 8.0)));
            Map<String, Object> result = Map.of("jobId", job.jobId, "assigned", job.accepted, "routeCount", routeCount, "lateCount", Math.max(0, job.accepted / 100), "runtimeMs", Math.max(1, System.currentTimeMillis() - started));
            writeLake("dispatch-results", job.tenantId, List.of(result));
            event(job.jobId, "BUFFER_MERGED", Map.of("microBatchMs", 750, "orders", job.accepted));
            event(job.jobId, "ROUTE_ASSIGNED", result);
            job.status = "COMPLETED";
            job.completedAt = Instant.now().toString();
            job.runtimeMs = System.currentTimeMillis() - started;
            completedJobs.incrementAndGet();
            totalLatencyMs.addAndGet(job.runtimeMs);
            event(job.jobId, "ARTIFACT_WRITTEN", Map.of("lake", lakeSummary(), "manifest", links(job.jobId).get("artifacts")));
            event(job.jobId, "COMPLETED", Map.of("runtimeMs", job.runtimeMs));
        } catch (Exception exception) {
            job.attempts++;
            failedJobs.incrementAndGet();
            job.status = job.attempts >= 3 || job.forceFail ? "DEAD_LETTER" : "FAILED";
            if ("DEAD_LETTER".equals(job.status)) deadLetterJobs.incrementAndGet();
            event(job.jobId, "FAILED", Map.of("attempt", job.attempts, "status", job.status, "error", exception.getMessage() == null ? exception.getClass().getSimpleName() : exception.getMessage()));
        } finally {
            activeWorkers.decrementAndGet();
        }
    }

    private void writeLake(String dataset, String tenantId, List<Map<String, Object>> rows) throws IOException {
        if (rows == null || rows.isEmpty()) return;
        Path path = Path.of("data", "irx-lake", safe(dataset), "dt=" + LocalDate.now(), "tenant=" + safe(tenantId), "part-00000.jsonl");
        Files.createDirectories(path.getParent());
        StringBuilder builder = new StringBuilder();
        for (Map<String, Object> row : rows) builder.append(objectMapper.writeValueAsString(row)).append(System.lineSeparator());
        byte[] bytes = builder.toString().getBytes(StandardCharsets.UTF_8);
        Files.write(path, bytes, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        lakeBytesWritten.addAndGet(bytes.length);
        lakeRowsWritten.addAndGet(rows.size());
    }

    private void event(String jobId, String type, Map<String, Object> data) {
        RuntimeEvent event = new RuntimeEvent("BDE-" + sequence.incrementAndGet(), jobId, type, Instant.now().toString(), data == null ? Map.of() : data);
        boundedAdd(jobEvents.computeIfAbsent(jobId, ignored -> new ConcurrentLinkedDeque<>()), event, MAX_JOB_EVENTS);
        boundedAdd(recentEvents, event, MAX_EVENT_BUFFER);
    }

    private static <T> void boundedAdd(Deque<T> deque, T value, int max) {
        deque.addLast(value);
        while (deque.size() > max) deque.pollFirst();
    }

    private static <T> List<T> tail(Deque<T> deque, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 1_000));
        List<T> rows = new ArrayList<>(deque);
        int start = Math.max(0, rows.size() - safeLimit);
        return rows.subList(start, rows.size());
    }

    private Map<String, Object> jobView(RuntimeJob job) {
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("jobId", job.jobId);
        view.put("batchId", job.batchId);
        view.put("tenantId", job.tenantId);
        view.put("kind", job.kind);
        view.put("lane", job.lane);
        view.put("status", job.status);
        view.put("accepted", job.accepted);
        view.put("rejected", job.rejected);
        view.put("attempts", job.attempts);
        view.put("createdAt", job.createdAt);
        view.put("startedAt", job.startedAt);
        view.put("completedAt", job.completedAt);
        view.put("runtimeMs", job.runtimeMs);
        view.put("links", links(job.jobId));
        return view;
    }

    private Map<String, Object> links(String jobId) {
        return Map.of("self", "/api/v1/bigdata/jobs/" + jobId, "events", "/api/v1/bigdata/jobs/" + jobId + "/events", "eventStream", "/api/v1/bigdata/jobs/" + jobId + "/events/stream", "artifacts", "/api/v1/bigdata/lake/summary");
    }

    private Map<String, Object> laneSummary() {
        Map<String, Map<String, Long>> lanes = new LinkedHashMap<>();
        for (String lane : List.of("ORDERS", "DRIVERS", "TELEMETRY", "LIVE_DISPATCH", "EXPORT", "DLQ")) {
            long queued = jobs.values().stream().filter(job -> lane.equals(job.lane) && "QUEUED".equals(job.status)).count();
            long runningJobs = jobs.values().stream().filter(job -> lane.equals(job.lane) && "RUNNING".equals(job.status)).count();
            long completed = jobs.values().stream().filter(job -> lane.equals(job.lane) && "COMPLETED".equals(job.status)).count();
            lanes.put(lane, Map.of("queued", queued, "running", runningJobs, "completed", completed));
        }
        return Map.copyOf(lanes);
    }

    private static int rejectCount(List<Map<String, Object>> items) {
        int rejected = 0;
        for (Map<String, Object> item : items) if (Boolean.TRUE.equals(item.get("invalid")) || "true".equals(String.valueOf(item.get("invalid")))) rejected++;
        return rejected;
    }

    private static boolean forceFail(IngestRequest request) {
        return request.options() != null && Boolean.TRUE.equals(request.options().get("forceFail"));
    }

    private static String normalizeKind(String kind) {
        return blank(kind) ? "orders" : kind.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9-]", "");
    }

    private static String laneFor(String kind) {
        if (kind.contains("driver")) return "DRIVERS";
        if (kind.contains("telemetry")) return "TELEMETRY";
        if (kind.contains("live")) return "LIVE_DISPATCH";
        if (kind.contains("export")) return "EXPORT";
        return "ORDERS";
    }

    private static String safe(String value) {
        return (blank(value) ? "unknown" : value).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9-_]", "-");
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    private static double number(Object value, double fallback) {
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private static String zoneFromLatLng(Map<String, Object> item) {
        double lat = number(item.getOrDefault("lat", item.get("pickupLat")), 10.77);
        double lng = number(item.getOrDefault("lng", item.get("pickupLng")), 106.70);
        if (lat > 10.82) return "north-hcm";
        if (lat < 10.75) return "south-hcm";
        if (lng > 106.73) return "east-hcm";
        if (lng < 106.67) return "west-hcm";
        return "central-hcm";
    }

    public record IngestRequest(String batchId, String tenantId, List<Map<String, Object>> items, Map<String, Object> options) {}
    public record SubmitResult(String jobId, String batchId, String tenantId, String kind, String lane, String status, int accepted, int rejected, int queueDepth, Map<String, Object> links) {}
    public record RuntimeEvent(String eventId, String jobId, String type, String timestamp, Map<String, Object> data) {
        Map<String, Object> asMap() { return Map.of("eventId", eventId, "jobId", jobId, "type", type, "timestamp", timestamp, "data", data); }
    }

    private static final class RuntimeJob {
        private final String jobId;
        private final String batchId;
        private final String tenantId;
        private final String kind;
        private final String lane;
        private final List<Map<String, Object>> items;
        private final int accepted;
        private final int rejected;
        private final boolean forceFail;
        private final String createdAt;
        private volatile String status = "QUEUED";
        private volatile int attempts;
        private volatile String startedAt = "";
        private volatile String completedAt = "";
        private volatile long runtimeMs;

        private RuntimeJob(String jobId, String batchId, String tenantId, String kind, String lane, List<Map<String, Object>> items, int accepted, int rejected, boolean forceFail, String createdAt) {
            this.jobId = jobId;
            this.batchId = batchId;
            this.tenantId = tenantId;
            this.kind = kind;
            this.lane = lane;
            this.items = Collections.unmodifiableList(new ArrayList<>(Objects.requireNonNullElse(items, List.of())));
            this.accepted = Math.max(0, accepted);
            this.rejected = Math.max(0, rejected);
            this.forceFail = forceFail;
            this.createdAt = createdAt;
        }
    }
}
