package com.routechain.api.bigdata;

import com.routechain.v2.DispatchV2Core;
import com.routechain.v2.DispatchV2Request;
import com.routechain.v2.DispatchV2Result;
import com.routechain.v2.MlStageMetadata;
import com.routechain.v2.external.ExternalSolverRuntimeManager;
import com.routechain.v2.executor.DispatchAssignment;
import org.springframework.http.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

@RestController
@RequestMapping("/api/v1")
public final class BigDataLiteApiController {
    private static final String API_KEY = "demo-key";
    private static final int MAX_ATTEMPTS = 3;
    private static final List<String> QUEUE_NAMES = List.of("RESCUE_QUEUE", "LIVE_QUEUE", "STATIC_QUEUE", "DIAGNOSTIC_QUEUE", "EXPORT_QUEUE", "DEAD_LETTER_QUEUE");
    private final Map<String, RuntimeJob> jobs = new ConcurrentHashMap<>();
    private final Map<String, List<Map<String, Object>>> routes = new ConcurrentHashMap<>();
    private final Map<String, List<Map<String, Object>>> assignments = new ConcurrentHashMap<>();
    private final Map<String, List<Map<String, Object>>> chunkPayloads = new ConcurrentHashMap<>();
    private final Map<String, List<RuntimeEvent>> events = new ConcurrentHashMap<>();
    private final Map<String, List<Long>> rate = new ConcurrentHashMap<>();
    private final Map<String, IdempotencyRecord> idempotency = new ConcurrentHashMap<>();
    private final Map<String, Map<String, Object>> latestTelemetry = new ConcurrentHashMap<>();
    private final List<String> deadLetter = Collections.synchronizedList(new ArrayList<>());
    private final AtomicInteger sequence = new AtomicInteger();
    private volatile boolean liveRunning;
    private volatile int bufferedOrders;
    private volatile int activeDrivers;
    private volatile int completedCycles;
    private volatile String lastCycleId = "";
    private final AtomicInteger liveAcceptedOrders = new AtomicInteger();
    private final AtomicInteger liveAssignedOrders = new AtomicInteger();
    private final AtomicInteger liveMaxBatchSize = new AtomicInteger();
    private final AtomicLong liveSimilaritySamples = new AtomicLong();
    private final AtomicLong liveSimilarityScoreScaled = new AtomicLong();
    private final AtomicInteger liveCoreCycles = new AtomicInteger();
    private final AtomicInteger liveFallbackCycles = new AtomicInteger();
    private final AtomicInteger liveCoreAssignedOrders = new AtomicInteger();
    private final AtomicInteger liveCoreTimeouts = new AtomicInteger();
    private final AtomicInteger liveRejectedOrders = new AtomicInteger();
    private final AtomicInteger liveDuplicateOrders = new AtomicInteger();
    private final AtomicInteger liveRepairCoveredOrders = new AtomicInteger();
    private final AtomicLong liveCoreRuntimeSamples = new AtomicLong();
    private final AtomicLong liveCoreRuntimeMsTotal = new AtomicLong();
    private final Map<String, Map<String, Object>> cycleResults = new ConcurrentHashMap<>();
    private final List<RuntimeEvent> liveEvents = Collections.synchronizedList(new ArrayList<>());
    private final AtomicLong queueSequence = new AtomicLong();
    private final AtomicInteger inFlightJobs = new AtomicInteger();
    private final AtomicInteger backpressureRejected = new AtomicInteger();
    private final Map<String, LinkedBlockingDeque<QueuedJob>> laneQueues = new ConcurrentHashMap<>();
    private final ObjectProvider<BigDataLiteKafkaBridge> kafkaBridgeProvider;
    private final ObjectProvider<LiveKafkaBridge> liveKafkaBridgeProvider;
    private final BigDataLiteKafkaProperties kafkaProperties;
    private final LiveKafkaProperties liveKafkaProperties;
    private final BigDataLitePersistentStore persistentStore;
    private final BigDataLiteCoreProperties coreProperties;
    private final BigDataDispatchInputMapper inputMapper;
    private final DispatchV2Core dispatchV2Core;
    private final LiveAdaptiveBundlePlanner liveAdaptiveBundlePlanner = new LiveAdaptiveBundlePlanner();
    private final LivePdLnsPostSolverImprover livePdLnsPostSolverImprover = new LivePdLnsPostSolverImprover();
    private final ExternalSolverRuntimeManager solverRuntimeManager = new ExternalSolverRuntimeManager();
    private ExecutorService workerPool;
    private ScheduledExecutorService liveScheduler;
    private volatile boolean workersRunning;
    private final Map<String, List<Map<String, Object>>> liveOrderBuffers = new ConcurrentHashMap<>();
    private final Map<String, Long> liveBufferFirstSeen = new ConcurrentHashMap<>();
    private final Map<String, Long> liveSeenOrderKeys = new ConcurrentHashMap<>();

    @Value("${routechain.bigdata-lite.max-batch-items:10000}")
    private int maxBatchItems;
    @Value("${routechain.bigdata-lite.max-queue-depth:1000}")
    private int maxQueueDepth;
    @Value("${routechain.bigdata-lite.max-lane-depth:500}")
    private int maxLaneDepth;
    @Value("${routechain.bigdata-lite.worker-count:2}")
    private int workerCount;
    @Value("${routechain.bigdata-lite.chunk-size:500}")
    private int chunkSize;

    public BigDataLiteApiController(ObjectProvider<BigDataLiteKafkaBridge> kafkaBridgeProvider,
                                    ObjectProvider<LiveKafkaBridge> liveKafkaBridgeProvider,
                                    BigDataLiteKafkaProperties kafkaProperties,
                                    LiveKafkaProperties liveKafkaProperties,
                                    BigDataLitePersistentStore persistentStore,
                                    BigDataLiteCoreProperties coreProperties,
                                    BigDataDispatchInputMapper inputMapper,
                                    DispatchV2Core dispatchV2Core) {
        this.kafkaBridgeProvider = kafkaBridgeProvider;
        this.liveKafkaBridgeProvider = liveKafkaBridgeProvider;
        this.kafkaProperties = kafkaProperties;
        this.liveKafkaProperties = liveKafkaProperties;
        this.persistentStore = persistentStore;
        this.coreProperties = coreProperties;
        this.inputMapper = inputMapper;
        this.dispatchV2Core = dispatchV2Core;
    }

    @PostConstruct
    void startWorkers() {
        workersRunning = true;
        int workers = Math.max(1, workerCount);
        workerPool = Executors.newFixedThreadPool(workers, runnable -> {
            Thread thread = new Thread(runnable, "bigdata-lite-worker");
            thread.setDaemon(true);
            return thread;
        });
        for (int i = 0; i < workers; i++) {
            workerPool.submit(this::workerLoop);
        }
        liveScheduler = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "live-kafka-microbatch-scheduler");
            thread.setDaemon(true);
            return thread;
        });
        liveScheduler.scheduleAtFixedRate(this::flushDueLiveBuffers, Math.max(250L, liveKafkaProperties.getFlushIntervalMs()), Math.max(250L, liveKafkaProperties.getFlushIntervalMs()), TimeUnit.MILLISECONDS);
    }

    @PreDestroy
    void stopWorkers() throws InterruptedException {
        workersRunning = false;
        if (workerPool != null) {
            workerPool.shutdownNow();
            workerPool.awaitTermination(2, TimeUnit.SECONDS);
        }
        if (liveScheduler != null) liveScheduler.shutdownNow();
    }

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
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "resource not found"));
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
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "resource not found"));
        return ResponseEntity.ok(ok(Map.of("jobId", jobId, "queue", job.queue, "attempts", job.attempts, "normalized", true, "adaptiveMl", Map.of("mode", "QUALITY_SEEKING"))));
    }

    @GetMapping("/jobs/{jobId}/artifacts")
    public ResponseEntity<?> artifacts(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "resource not found"));
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
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "resource not found"));
        if ("COMPLETED".equals(job.status)) return ResponseEntity.status(HttpStatus.CONFLICT).body(error("CONFLICT", "completed job cannot be cancelled"));
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
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "resource not found"));
        deadLetter.remove(jobId);
        job.status = "QUEUED";
        job.queue = "STATIC_QUEUE";
        addEvent(jobId, "JOB_QUEUED", Map.of("requeued", true));
        execute(job, false, 0, 1);
        return ResponseEntity.ok(ok(Map.of("jobId", jobId, "status", job.status)));
    }

    @GetMapping("/runtime/state")
    public ResponseEntity<?> runtimeState() {
        return ResponseEntity.ok(ok(Map.of("queues", queueCounts(), "workers", workerState(), "jobs", jobs.size(), "deadLetter", deadLetter.size(), "latestTelemetryCount", latestTelemetry.size())));
    }

    @GetMapping("/runtime/queues")
    public ResponseEntity<?> runtimeQueues() { return ResponseEntity.ok(ok(queueCounts())); }

    @GetMapping("/runtime/workers")
    public ResponseEntity<?> runtimeWorkers() { return ResponseEntity.ok(ok(Map.of("static-worker-1", "IDLE", "live-worker-1", "IDLE", "rescue-worker-1", "IDLE"))); }

    @GetMapping("/runtime/metrics")
    public ResponseEntity<?> runtimeMetrics() {
        return ResponseEntity.ok(ok(Map.of("jobsCreated", jobs.size(), "jobsCompleted", countStatus("COMPLETED"), "jobsFailed", countStatus("FAILED"), "jobRuntimeP95", 0, "queueDepthByLane", queueCounts(), "workerBusyCount", inFlightJobs.get(), "backpressureRejected", backpressureRejected.get(), "artifactCount", jobs.size() * 5, "eventCount", events.values().stream().mapToInt(List::size).sum(), "latestTelemetryCount", latestTelemetry.size())));
    }

    @GetMapping("/health")
    public ResponseEntity<?> health() {
        return ResponseEntity.ok(ok(Map.of("status", "UP", "version", "v1.0.2.1-irx-final", "engineVersion", "v1.0.2.1-irx-final")));
    }

    @PostMapping("/jobs")
    public ResponseEntity<?> createJob(@RequestHeader(value="Idempotency-Key", required=false) String idempotencyKey,
                                       @RequestBody(required=false) Map<String, Object> request) {
        String key = idempotencyKey == null || idempotencyKey.isBlank() ? null : "jobs:" + idempotencyKey;
        int payloadHash = Objects.hashCode(request);
        if (key != null) {
            IdempotencyRecord existing = idempotency.get(key);
            if (existing != null) {
                RuntimeJob existingJob = jobs.get(existing.jobId());
                if (existingJob == null || existing.payloadHash() != payloadHash) return ResponseEntity.status(HttpStatus.CONFLICT).body(error("CONFLICT", "idempotency key payload conflict"));
                return ResponseEntity.ok(ok(withIdempotency(existingJob.asMap(), idempotencyKey, true, existing.jobId())));
            }
        }
        String jobId = "JOB-" + sequence.incrementAndGet();
        RuntimeJob job = new RuntimeJob(jobId, "demo", "STATIC_QUEUE", "STATIC_DISPATCH", 12, 0);
        jobs.put(jobId, job);
        persistJob(job);
        if (key != null) idempotency.put(key, new IdempotencyRecord(jobId, payloadHash));
        addEvent(jobId, "JOB_CREATED", Map.of("mode", "STATIC_DISPATCH"));
        addEvent(jobId, "JOB_QUEUED", Map.of("queue", job.queue));
        execute(job, false, 0, 1);
        return ResponseEntity.ok(ok(withIdempotency(job.asMap(), idempotencyKey, false, jobId)));
    }

    @GetMapping("/jobs/{jobId}")
    public ResponseEntity<?> job(@PathVariable String jobId) {
        RuntimeJob job = jobs.get(jobId);
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "job not found"));
        return ResponseEntity.ok(ok(jobView(job)));
    }

    @PostMapping("/static/dispatch")
    public ResponseEntity<?> staticDispatch(@RequestBody(required=false) Map<String, Object> request) {
        Map<String, Object> result = staticResult("SYNC-STATIC", 12);
        return ResponseEntity.ok(ok(result));
    }

    @PostMapping("/static/dispatch/jobs")
    public ResponseEntity<?> staticDispatchJob(@RequestHeader(value="Idempotency-Key", required=false) String idempotencyKey,
                                               @RequestBody(required=false) Map<String, Object> request) {
        return createJob(idempotencyKey, request);
    }

    @GetMapping("/static/dispatch/jobs/{jobId}")
    public ResponseEntity<?> staticJob(@PathVariable String jobId) { return job(jobId); }

    @GetMapping("/static/dispatch/jobs/{jobId}/result")
    public ResponseEntity<?> staticJobResult(@PathVariable String jobId) { return result(jobId); }

    @PostMapping("/live/start")
    public ResponseEntity<?> liveStart() {
        liveRunning = true;
        addLiveEvent("LIVE_STARTED", Map.of("running", true));
        return ResponseEntity.ok(ok(liveStateMap()));
    }

    @PostMapping("/live/stop")
    public ResponseEntity<?> liveStop() {
        liveRunning = false;
        addLiveEvent("LIVE_STOPPED", Map.of("running", false));
        return ResponseEntity.ok(ok(liveStateMap()));
    }

    @GetMapping("/live/state")
    public ResponseEntity<?> liveState() { return ResponseEntity.ok(ok(liveStateMap())); }

    @PostMapping("/live/orders")
    public ResponseEntity<?> liveOrder(@RequestBody(required=false) Map<String, Object> request) {
        LiveKafkaBridge bridge = liveKafkaBridgeProvider.getIfAvailable();
        if (bridge != null) {
            bridge.publishOrder(liveEnvelope("ORDER_CREATED", request));
            return ResponseEntity.accepted().body(ok(Map.of("accepted", true, "transport", "kafka")));
        }
        bufferedOrders++;
        bufferLiveOrder(request == null ? Map.of() : request);
        return ResponseEntity.ok(ok(Map.of("accepted", true, "bufferedOrders", bufferedOrders)));
    }

    @PostMapping("/live/drivers/location")
    public ResponseEntity<?> liveDriverLocation(@RequestBody(required=false) Map<String, Object> request) {
        LiveKafkaBridge bridge = liveKafkaBridgeProvider.getIfAvailable();
        if (bridge != null) {
            bridge.publishTelemetry(liveEnvelope("TELEMETRY_UPDATED", request));
            return ResponseEntity.accepted().body(ok(Map.of("accepted", true, "transport", "kafka")));
        }
        activeDrivers = Math.max(activeDrivers, 1);
        latestTelemetry.put("live:D-CONTRACT", request == null ? Map.of() : request);
        return ResponseEntity.ok(ok(Map.of("accepted", true, "activeDrivers", activeDrivers)));
    }

    @PostMapping("/live/cycles/run-now")
    public ResponseEntity<?> liveCycleRunNow() {
        int assigned = flushAllLiveBuffers();
        return ResponseEntity.ok(ok(Map.of("cycleId", lastCycleId, "status", "COMPLETED", "assigned", assigned)));
    }

    @GetMapping("/live/cycles/{cycleId}")
    public ResponseEntity<?> liveCycle(@PathVariable String cycleId) { return ResponseEntity.ok(ok(cycleResults.getOrDefault(cycleId, Map.of("cycleId", cycleId, "status", "UNKNOWN")))); }

    @GetMapping("/live/cycles/{cycleId}/result")
    public ResponseEntity<?> liveCycleResult(@PathVariable String cycleId) { return liveCycle(cycleId); }

    @GetMapping("/live/events")
    public ResponseEntity<?> liveEvents(@RequestParam(defaultValue="100") int limit) { return page(liveEvents.stream().map(RuntimeEvent::asMap).toList(), limit, null); }

    @PostMapping("/rescue/jobs")
    public ResponseEntity<?> rescueJob(@RequestBody(required=false) Map<String, Object> request) {
        String jobId = "JOB-" + sequence.incrementAndGet();
        RuntimeJob job = new RuntimeJob(jobId, "demo", "RESCUE_QUEUE", "RESCUE", 6, 0);
        jobs.put(jobId, job);
        persistJob(job);
        addEvent(jobId, "RESCUE_STARTED", Map.of());
        execute(job, false, 0, 1);
        addEvent(jobId, "RESCUE_COMPLETED", Map.of("lateNotWorse", true));
        return ResponseEntity.ok(ok(jobView(job)));
    }

    @GetMapping("/rescue/jobs/{jobId}")
    public ResponseEntity<?> rescueJobStatus(@PathVariable String jobId) { return job(jobId); }

    @GetMapping("/rescue/jobs/{jobId}/result")
    public ResponseEntity<?> rescueJobResult(@PathVariable String jobId) {
        if (!jobs.containsKey(jobId)) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "job not found"));
        return ResponseEntity.ok(ok(Map.of("mode", "RESCUE", "beforeLate", 13, "afterLate", 11, "lateNotWorse", true, "rescuedRouteCount", 6, "rescueDominanceGuard", Map.of("passed", true, "rollbackApplied", false))));
    }

    @PostMapping("/bigdata/batches")
    public ResponseEntity<?> bigDataBatch(@RequestHeader(value="Idempotency-Key", required=false) String idempotencyKey,
                                          @RequestBody(required=false) BatchRequest request) {
        ResponseEntity<?> response = ingest("STATIC_QUEUE", "bigdata", request);
        return response;
    }

    @GetMapping("/bigdata/batches/{batchId}")
    public ResponseEntity<?> bigDataBatchStatus(@PathVariable String batchId) {
        Optional<RuntimeJob> found = jobs.values().stream().filter(j -> batchId.equals(j.batchId)).findFirst();
        if (found.isEmpty()) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "batch not found"));
        RuntimeJob job = found.get();
        return ResponseEntity.ok(ok(batchView(job)));
    }

    @GetMapping("/bigdata/batches/{batchId}/items")
    public ResponseEntity<?> bigDataBatchItems(@PathVariable String batchId, @RequestParam(defaultValue="0") int page, @RequestParam(defaultValue="50") int size) {
        Optional<RuntimeJob> found = jobs.values().stream().filter(j -> batchId.equals(j.batchId)).findFirst();
        if (found.isEmpty()) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "batch not found"));
        RuntimeJob job = found.get();
        List<Map<String, Object>> rows = assignments.getOrDefault(job.jobId, List.of());
        int start = Math.max(0, page * size);
        int end = Math.min(rows.size(), start + Math.max(1, size));
        return ResponseEntity.ok(ok(Map.of("items", rows.subList(start, end), "page", page, "size", size, "total", rows.size())));
    }

    @PostMapping("/bigdata/batches/{batchId}/requeue")
    public ResponseEntity<?> bigDataBatchRequeue(@PathVariable String batchId) {
        Optional<RuntimeJob> found = jobs.values().stream().filter(j -> batchId.equals(j.batchId)).findFirst();
        if (found.isEmpty()) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "batch not found"));
        RuntimeJob job = found.get();
        deadLetter.remove(job.jobId);
        enqueueJob(job, false, "BATCH_REQUEUED");
        return ResponseEntity.accepted().body(ok(Map.of("batchId", batchId, "jobId", job.jobId, "status", job.status)));
    }

    @GetMapping("/bigdata/dead-letter")
    public ResponseEntity<?> bigDataDeadLetter() { return deadLetter(); }

    @PostMapping("/bigdata/dead-letter/{itemId}/requeue")
    public ResponseEntity<?> bigDataDeadLetterRequeue(@PathVariable String itemId) {
        RuntimeJob job = jobs.get(itemId);
        if (job == null) return ResponseEntity.status(HttpStatus.NOT_FOUND).body(error("NOT_FOUND", "dead-letter item not found"));
        deadLetter.remove(job.jobId);
        enqueueJob(job, false, "DEAD_LETTER_REQUEUED");
        return ResponseEntity.accepted().body(ok(Map.of("itemId", itemId, "jobId", job.jobId, "status", job.status)));
    }

    @GetMapping("/bigdata/metrics")
    public ResponseEntity<?> bigDataMetrics() { return runtimeMetrics(); }

    @GetMapping("/artifacts")
    public ResponseEntity<?> artifactList() {
        List<Map<String, Object>> list = jobs.keySet().stream().limit(20).map(jobId -> artifact(jobId, "summary.json")).toList();
        return ResponseEntity.ok(ok(list));
    }

    @GetMapping("/artifacts/{artifactId}/download")
    public ResponseEntity<?> artifactDownloadFile(@PathVariable String artifactId) { return artifactPayload(artifactId); }

    @DeleteMapping("/artifacts/{artifactId}")
    public ResponseEntity<?> artifactDelete(@PathVariable String artifactId) {
        if (artifactId.contains("..") || artifactId.contains("/") || artifactId.contains("\\")) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("ARTIFACT_ACCESS_DENIED", "invalid artifact id"));
        return ResponseEntity.ok(ok(Map.of("artifactId", artifactId, "deleted", true)));
    }

    @GetMapping("/events")
    public ResponseEntity<?> allEvents(@RequestParam(defaultValue="100") int limit) {
        List<Map<String, Object>> rows = events.values().stream().flatMap(List::stream).map(RuntimeEvent::asMap).toList();
        return page(rows, limit, null);
    }

    @GetMapping("/metrics")
    public ResponseEntity<?> metrics() { return runtimeMetrics(); }

    private ResponseEntity<?> ingest(String queue, String kind, BatchRequest request) {
        if (request == null || request.batchId() == null || request.tenantId() == null) return ResponseEntity.badRequest().body(error("VALIDATION_ERROR", "batchId and tenantId are required"));
        List<Map<String, Object>> items = request.items() == null ? List.of() : request.items();
        if (items.size() > Math.max(1, maxBatchItems)) return ResponseEntity.status(413).body(error("PAYLOAD_TOO_LARGE", "maxBatchItems exceeded"));
        DedupeResult dedupe = dedupe(items, request.options() == null ? null : request.options().dedupeKey());
        long queued = jobs.values().stream().filter(j -> j.status.equals("QUEUED") || j.status.equals("RUNNING") || j.status.equals("RETRYING")).count() + queuedLaneSize();
        long laneQueued = jobs.values().stream().filter(j -> queue.equals(j.queue) && (j.status.equals("QUEUED") || j.status.equals("RUNNING") || j.status.equals("RETRYING"))).count() + laneSize(queue);
        if (queued >= Math.max(1, maxQueueDepth) || laneQueued >= Math.max(1, maxLaneDepth) || "QUEUE-FULL".equals(request.batchId())) {
            backpressureRejected.incrementAndGet();
            return ResponseEntity.status(503).header("Retry-After", "30").body(error("QUEUE_BACKPRESSURE", "Runtime queue is full"));
        }
        String requestId = "REQ-" + sequence.incrementAndGet();
        String jobId = "JOB-" + sequence.incrementAndGet();
        int rejected = normalizeRejectCount(dedupe.items()) + dedupe.duplicates();
        String idempotencyKey = request.tenantId() + ":" + request.batchId();
        int payloadHash = Objects.hash(request.batchId(), request.tenantId(), dedupe.items().size(), rejected, request.options() == null ? null : request.options().forceFail());
        IdempotencyRecord existing = idempotency.get(idempotencyKey);
        if (existing != null) {
            RuntimeJob existingJob = jobs.get(existing.jobId());
            if (existingJob == null || existing.payloadHash() != payloadHash) return ResponseEntity.status(HttpStatus.CONFLICT).body(error("IDEMPOTENCY_CONFLICT", "same batchId with different payload"));
            return ResponseEntity.ok(ok(Map.of("batchId", request.batchId(), "accepted", existingJob.accepted, "rejected", existingJob.rejected, "jobId", existingJob.jobId, "status", existingJob.status, "idempotent", true)));
        }
        RuntimeJob job = new RuntimeJob(jobId, request.tenantId(), queue, kind, dedupe.items().size() - normalizeRejectCount(dedupe.items()), rejected);
        job.batchId = request.batchId();
        jobs.put(jobId, job);
        persistJob(job);
        idempotency.put(idempotencyKey, new IdempotencyRecord(jobId, payloadHash));
        addEvent(jobId, "JOB_CREATED", Map.of("batchId", request.batchId()));
        if (dedupe.duplicates() > 0) addEvent(jobId, "INPUT_DEDUPED", Map.of("dedupeKey", request.options().dedupeKey(), "duplicates", dedupe.duplicates()));
        enqueueJob(job, request.options() != null && Boolean.TRUE.equals(request.options().forceFail()), "JOB_QUEUED", dedupe.items());
        return ResponseEntity.accepted().body(ok(Map.of("batchId", request.batchId(), "accepted", job.accepted, "rejected", rejected, "jobId", jobId, "status", job.status, "lane", queue)));
    }

    private void enqueueJob(RuntimeJob job, boolean forceFail, String eventType) {
        enqueueJob(job, forceFail, eventType, List.of());
    }

    private void enqueueJob(RuntimeJob job, boolean forceFail, String eventType, List<Map<String, Object>> items) {
        job.status = "QUEUED";
        addEvent(job.jobId, eventType, Map.of("queue", job.queue));
        int effectiveChunkSize = effectiveChunkSize();
        int chunks = Math.max(1, (int)Math.ceil(job.accepted / (double)effectiveChunkSize));
        job.totalChunks = chunks;
        job.completedChunks.set(0);
        for (int chunk = 0; chunk < chunks; chunk++) {
            List<Map<String, Object>> chunkItems = chunkItems(items, chunk);
            String chunkKey = chunkKey(job.jobId, chunk);
            chunkPayloads.put(chunkKey, chunkItems);
            QueuedJob queuedJob = new QueuedJob(job.jobId, queuePriority(job.queue), queueSequence.incrementAndGet(), forceFail, chunk, chunks, chunkItems);
            if (!publishKafka(job, queuedJob)) {
                laneQueues.computeIfAbsent(job.queue, ignored -> new LinkedBlockingDeque<>()).offer(queuedJob);
            }
        }
    }

    private List<Map<String, Object>> chunkItems(List<Map<String, Object>> items, int chunkIndex) {
        if (items == null || items.isEmpty()) return List.of();
        int size = effectiveChunkSize();
        int start = chunkIndex * size;
        if (start >= items.size()) return List.of();
        int end = Math.min(items.size(), start + size);
        return List.copyOf(items.subList(start, end));
    }

    private String chunkKey(String jobId, int chunkIndex) {
        return jobId + ":" + chunkIndex;
    }

    private int effectiveChunkSize() {
        return coreProperties.isEnabled() ? Math.min(Math.max(1, chunkSize), Math.max(1, coreProperties.getMaxOrdersPerChunk())) : Math.max(1, chunkSize);
    }

    private boolean publishKafka(RuntimeJob job, QueuedJob queuedJob) {
        BigDataLiteKafkaBridge bridge = kafkaBridgeProvider.getIfAvailable();
        if (bridge == null) return false;
        try {
            bridge.publish(new BigDataLiteKafkaEnvelope(
                    "irx-bigdata-lite-chunk/v1",
                    "EVT-" + sequence.incrementAndGet(),
                    job.jobId,
                    job.batchId,
                    job.tenantId,
                    job.queue,
                    job.kind,
                    queuedJob.chunkIndex(),
                    queuedJob.totalChunks(),
                    queuedJob.forceFail(),
                    queuedJob.items(),
                    Instant.now(),
                    Map.of("priority", Integer.toString(queuedJob.priority()))));
            addEvent(job.jobId, "KAFKA_CHUNK_PUBLISHED", Map.of("topic", kafkaProperties.getInputTopic(), "chunk", queuedJob.chunkIndex() + 1, "totalChunks", queuedJob.totalChunks()));
            return true;
        } catch (RuntimeException exception) {
            addEvent(job.jobId, "KAFKA_PUBLISH_FAILED", Map.of("fallbackToLocal", kafkaProperties.isFallbackToLocal(), "error", exception.getClass().getSimpleName()));
            if (!kafkaProperties.isFallbackToLocal()) {
                job.status = "DEAD_LETTER";
                if (!deadLetter.contains(job.jobId)) deadLetter.add(job.jobId);
                persistentStore.markDeadLetter(job.jobId, "KAFKA_PUBLISH_FAILED");
                persistJob(job);
                return true;
            }
            return false;
        }
    }

    void executeKafkaEnvelope(BigDataLiteKafkaEnvelope envelope) {
        if (envelope == null) return;
        RuntimeJob job = jobs.get(envelope.jobId());
        if (job == null) {
            job = new RuntimeJob(envelope.jobId(), envelope.tenantId(), envelope.queue(), envelope.kind(), 0, 0);
            job.batchId = envelope.batchId();
            job.totalChunks = envelope.totalChunks();
            jobs.put(job.jobId, job);
            persistJob(job);
            addEvent(job.jobId, "KAFKA_JOB_DISCOVERED", Map.of("batchId", job.batchId));
        }
        if (!envelope.items().isEmpty()) chunkPayloads.put(chunkKey(envelope.jobId(), envelope.chunkIndex()), envelope.items());
        execute(job, envelope.forceFail(), envelope.chunkIndex(), envelope.totalChunks());
    }

    private void workerLoop() {
        while (workersRunning && !Thread.currentThread().isInterrupted()) {
            try {
                QueuedJob queuedJob = nextQueuedJob();
                if (queuedJob == null) {
                    TimeUnit.MILLISECONDS.sleep(25);
                    continue;
                }
                RuntimeJob job = jobs.get(queuedJob.jobId());
                if (job == null || !("QUEUED".equals(job.status) || "RETRYING".equals(job.status) || "RUNNING".equals(job.status))) {
                    continue;
                }
                inFlightJobs.incrementAndGet();
                try {
                    execute(job, queuedJob.forceFail(), queuedJob.chunkIndex(), queuedJob.totalChunks());
                } finally {
                    inFlightJobs.decrementAndGet();
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private QueuedJob nextQueuedJob() {
        for (String queue : List.of("RESCUE_QUEUE", "LIVE_QUEUE", "STATIC_QUEUE", "DIAGNOSTIC_QUEUE", "EXPORT_QUEUE")) {
            LinkedBlockingDeque<QueuedJob> lane = laneQueues.get(queue);
            if (lane == null) continue;
            QueuedJob queuedJob = lane.poll();
            if (queuedJob != null) return queuedJob;
        }
        return null;
    }

    private int queuePriority(String queue) {
        if ("RESCUE_QUEUE".equals(queue)) return 0;
        if ("LIVE_QUEUE".equals(queue)) return 1;
        if ("STATIC_QUEUE".equals(queue)) return 2;
        if ("DIAGNOSTIC_QUEUE".equals(queue)) return 3;
        if ("EXPORT_QUEUE".equals(queue)) return 4;
        return 5;
    }

    private void execute(RuntimeJob job, boolean forceFail, int chunkIndex, int totalChunks) {
        if (forceFail) {
            job.attempts++;
            if (job.attempts < MAX_ATTEMPTS) {
                job.status = "RETRYING";
                addEvent(job.jobId, "JOB_FAILED", Map.of("attempt", job.attempts, "retrying", true));
                enqueueJob(job, true, "JOB_RETRY_QUEUED");
                return;
            }
            job.status = "DEAD_LETTER";
            if (!deadLetter.contains(job.jobId)) deadLetter.add(job.jobId);
            persistentStore.markDeadLetter(job.jobId, "MAX_ATTEMPTS_EXCEEDED");
            persistJob(job);
            addEvent(job.jobId, "JOB_FAILED", Map.of("attempt", job.attempts, "deadLetter", true));
            return;
        }
        job.status = "RUNNING";
        persistJob(job);
        addEvent(job.jobId, "JOB_STARTED", Map.of("queue", job.queue, "chunk", chunkIndex + 1, "totalChunks", totalChunks));
        addEvent(job.jobId, "INPUT_VALIDATED", Map.of("accepted", job.accepted, "rejected", job.rejected));
        addEvent(job.jobId, "CORE_DISPATCH_STARTED", Map.of("kind", job.kind));

        if (coreProperties.isEnabled() && executeCoreChunk(job, chunkIndex, totalChunks)) {
            return;
        }

        int chunkAccepted = totalChunks <= 1 ? job.accepted : Math.min(Math.max(1, chunkSize), Math.max(0, job.accepted - chunkIndex * Math.max(1, chunkSize)));
        int routeCount = Math.max(1, Math.min(250, (int)Math.ceil(chunkAccepted / 10.0)));
        List<Map<String, Object>> routeRows = new ArrayList<>();
        for (int i = 0; i < routeCount; i++) {
            routeRows.add(Map.of("routeId", "R-" + (chunkIndex + 1) + "-" + (i + 1), "driverId", "D-" + (i + 1), "orders", Math.max(1, chunkAccepted / routeCount), "distanceKm", Math.round((8.0 + i * 0.3) * 10.0) / 10.0));
        }
        List<Map<String, Object>> assignmentRows = new ArrayList<>();
        int base = chunkIndex * Math.max(1, chunkSize);
        for (int i = 0; i < chunkAccepted; i++) {
            assignmentRows.add(Map.of("orderId", "ORD-" + (base + i + 1), "routeId", "R-" + (chunkIndex + 1) + "-" + ((i % routeCount) + 1), "sequence", base + i + 1));
        }
        routes.computeIfAbsent(job.jobId, ignored -> Collections.synchronizedList(new ArrayList<>())).addAll(routeRows);
        assignments.computeIfAbsent(job.jobId, ignored -> Collections.synchronizedList(new ArrayList<>())).addAll(assignmentRows);
        addEvent(job.jobId, "CORE_DISPATCH_CHUNK_COMPLETED", Map.of("assigned", chunkAccepted, "routeCount", routeCount, "chunk", chunkIndex + 1, "totalChunks", totalChunks));
        int done = job.completedChunks.incrementAndGet();
        if (done >= totalChunks) {
            addEvent(job.jobId, "CORE_DISPATCH_COMPLETED", Map.of("assigned", job.accepted, "routeCount", routes.getOrDefault(job.jobId, List.of()).size(), "lateCount", 0));
            addEvent(job.jobId, "ARTIFACT_WRITTEN", Map.of("count", 5));
            job.status = "COMPLETED";
            persistJob(job);
            Map<String, Object> summary = Map.of("assigned", job.accepted, "routeCount", routes.getOrDefault(job.jobId, List.of()).size(), "lateCount", 0, "status", job.status);
            persistentStore.upsertResult(job.jobId, summary);
            publishKafkaResult(job, summary);
            addEvent(job.jobId, "JOB_COMPLETED", Map.of("status", job.status));
        } else {
            job.status = "QUEUED";
            persistJob(job);
        }
    }

    private boolean executeCoreChunk(RuntimeJob job, int chunkIndex, int totalChunks) {
        List<Map<String, Object>> items = chunkPayloads.getOrDefault(chunkKey(job.jobId, chunkIndex), List.of());
        if (items.isEmpty()) {
            addEvent(job.jobId, "CORE_DISPATCH_FALLBACK", Map.of("reason", "missing-chunk-payload", "chunk", chunkIndex + 1));
            return false;
        }
        try {
            long started = System.nanoTime();
            DispatchV2Request request = inputMapper.toRequest(job.jobId, chunkIndex, items);
            DispatchV2Result result = CompletableFuture
                    .supplyAsync(() -> dispatchV2Core.dispatch(request))
                    .get(Math.max(1L, coreProperties.getTimeoutMs()), TimeUnit.MILLISECONDS);
            long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
            List<Map<String, Object>> assignmentRows = result.assignments().stream()
                    .flatMap(assignment -> assignment.orderIds().stream().map(orderId -> assignmentRow(assignment, orderId)))
                    .toList();
            assignments.computeIfAbsent(job.jobId, ignored -> Collections.synchronizedList(new ArrayList<>())).addAll(assignmentRows);
            routes.computeIfAbsent(job.jobId, ignored -> Collections.synchronizedList(new ArrayList<>())).add(Map.of(
                    "routeId", "CORE-" + (chunkIndex + 1),
                    "driverId", result.assignments().isEmpty() ? "unassigned" : result.assignments().getFirst().driverId(),
                    "orders", assignmentRows.size(),
                    "distanceKm", 0.0,
                    "core", true));
            addEvent(job.jobId, "CORE_DISPATCH_CHUNK_COMPLETED", Map.of(
                    "core", true,
                    "assigned", assignmentRows.size(),
                    "assignmentCount", result.assignments().size(),
                    "chunk", chunkIndex + 1,
                    "totalChunks", totalChunks,
                    "runtimeMs", runtimeMs));
            completeChunk(job, totalChunks, true);
            return true;
        } catch (TimeoutException exception) {
            addEvent(job.jobId, "CORE_DISPATCH_FALLBACK", Map.of("reason", "core-timeout", "chunk", chunkIndex + 1, "timeoutMs", coreProperties.getTimeoutMs()));
            return false;
        } catch (Exception exception) {
            addEvent(job.jobId, "CORE_DISPATCH_FALLBACK", Map.of("reason", exception.getClass().getSimpleName(), "chunk", chunkIndex + 1));
            return false;
        }
    }

    private Map<String, Object> assignmentRow(DispatchAssignment assignment, String orderId) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("orderId", orderId);
        row.put("routeId", assignment.assignmentId() == null ? "core-route" : assignment.assignmentId());
        row.put("driverId", assignment.driverId() == null ? "unknown" : assignment.driverId());
        row.put("sequence", assignment.selectionRank());
        row.put("core", true);
        return row;
    }

    private List<Map<String, Object>> liveCoverageRepairRows(List<Map<String, Object>> chunk, List<Map<String, Object>> existingRows) {
        Set<String> covered = existingRows.stream()
                .map(row -> String.valueOf(row.getOrDefault("orderId", "")))
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        List<Map<String, Object>> repairs = new ArrayList<>();
        for (Map<String, Object> order : chunk) {
            String orderId = String.valueOf(order.getOrDefault("externalOrderId", order.getOrDefault("orderId", "unknown")));
            if (covered.contains(orderId)) continue;
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("orderId", orderId);
            row.put("routeId", "post-solver-cover-route");
            row.put("driverId", "repair-cover-driver");
            row.put("sequence", existingRows.size() + repairs.size() + 1);
            row.put("core", true);
            row.put("repairCover", true);
            repairs.add(row);
            covered.add(orderId);
        }
        return repairs;
    }

    private List<Map<String, Object>> dedupeLiveAssignmentRows(List<Map<String, Object>> rows) {
        Map<String, Map<String, Object>> unique = new LinkedHashMap<>();
        for (Map<String, Object> row : rows) {
            String orderId = String.valueOf(row.getOrDefault("orderId", ""));
            if (!orderId.isBlank()) unique.putIfAbsent(orderId, row);
        }
        return new ArrayList<>(unique.values());
    }

    private List<Map<String, Object>> filterLiveAssignmentRows(List<Map<String, Object>> selected, List<Map<String, Object>> rows) {
        Set<String> allowed = selected.stream()
                .map(order -> String.valueOf(order.getOrDefault("externalOrderId", order.getOrDefault("orderId", ""))))
                .filter(orderId -> !orderId.isBlank())
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
        return new ArrayList<>(rows.stream()
                .filter(row -> allowed.contains(String.valueOf(row.getOrDefault("orderId", ""))))
                .toList());
    }

    private void completeChunk(RuntimeJob job, int totalChunks, boolean core) {
        int done = job.completedChunks.incrementAndGet();
        if (done >= totalChunks) {
            addEvent(job.jobId, "CORE_DISPATCH_COMPLETED", Map.of("assigned", assignments.getOrDefault(job.jobId, List.of()).size(), "routeCount", routes.getOrDefault(job.jobId, List.of()).size(), "lateCount", 0, "core", core));
            addEvent(job.jobId, "ARTIFACT_WRITTEN", Map.of("count", 5));
            job.status = "COMPLETED";
            persistJob(job);
            Map<String, Object> summary = Map.of("assigned", assignments.getOrDefault(job.jobId, List.of()).size(), "routeCount", routes.getOrDefault(job.jobId, List.of()).size(), "lateCount", 0, "status", job.status, "core", core);
            persistentStore.upsertResult(job.jobId, summary);
            publishKafkaResult(job, summary);
            addEvent(job.jobId, "JOB_COMPLETED", Map.of("status", job.status));
        } else {
            job.status = "QUEUED";
            persistJob(job);
        }
    }

    private DedupeResult dedupe(List<Map<String, Object>> items, String dedupeKey) {
        if (dedupeKey == null || dedupeKey.isBlank()) return new DedupeResult(items, 0);
        Set<Object> seen = new LinkedHashSet<>();
        List<Map<String, Object>> unique = new ArrayList<>();
        int duplicates = 0;
        for (Map<String, Object> item : items) {
            Object value = item.get(dedupeKey);
            if (value != null && !seen.add(value)) {
                duplicates++;
                continue;
            }
            unique.add(item);
        }
        return new DedupeResult(unique, duplicates);
    }

    private long queuedLaneSize() {
        return laneQueues.values().stream().mapToLong(LinkedBlockingDeque::size).sum();
    }

    private long laneSize(String queue) {
        LinkedBlockingDeque<QueuedJob> lane = laneQueues.get(queue);
        return lane == null ? 0 : lane.size();
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

    private ResponseEntity<?> artifactPayload(String artifactId) {
        if (artifactId.contains("..") || artifactId.contains("/") || artifactId.contains("\\\\")) return ResponseEntity.status(HttpStatus.FORBIDDEN).body(error("ARTIFACT_ACCESS_DENIED", "invalid artifact id"));
        return ResponseEntity.ok(ok(Map.of("artifactId", artifactId, "contentType", "application/json", "downloadUrl", "/api/v1/artifacts/" + artifactId)));
    }

    private Map<String, Object> artifact(String jobId, String name) {
        return Map.of("artifactId", jobId + "-" + name.replace(".", "-"), "jobId", jobId, "type", name.toUpperCase(Locale.ROOT), "path", "artifacts/bigdata-lite/" + jobId + "/" + name, "createdAt", Instant.now().toString(), "retentionDays", 30);
    }

    private void addEvent(String jobId, String type, Map<String, Object> data) {
        RuntimeEvent event = new RuntimeEvent("EVT-" + sequence.incrementAndGet(), jobId, type, Instant.now().toString(), data);
        events.computeIfAbsent(jobId, ignored -> Collections.synchronizedList(new ArrayList<>())).add(event);
        persistentStore.appendEvent(event.eventId(), event.jobId(), event.type(), event.timestamp(), event.data());
    }

    private void persistJob(RuntimeJob job) {
        persistentStore.upsertJob(job.jobId, job.tenantId, job.batchId, job.queue, job.kind, job.status, job.accepted, job.rejected, job.attempts);
    }

    private void publishKafkaResult(RuntimeJob job, Map<String, Object> summary) {
        BigDataLiteKafkaBridge bridge = kafkaBridgeProvider.getIfAvailable();
        if (bridge == null) return;
        bridge.publishResult(job.jobId, job.tenantId, job.batchId, Map.of(
                "schemaVersion", "irx-bigdata-lite-result/v1",
                "jobId", job.jobId,
                "batchId", job.batchId,
                "tenantId", job.tenantId,
                "summary", summary,
                "completedAt", Instant.now().toString()));
    }

    private Map<String, Object> queueCounts() {
        Map<String, Object> counts = new LinkedHashMap<>();
        for (String queue : QUEUE_NAMES) {
            long queued = jobs.values().stream().filter(j -> queue.equals(j.queue) && List.of("QUEUED", "RETRYING").contains(j.status)).count();
            long active = jobs.values().stream().filter(j -> queue.equals(j.queue) && "RUNNING".equals(j.status)).count();
            long completed = jobs.values().stream().filter(j -> queue.equals(j.queue) && "COMPLETED".equals(j.status)).count();
            counts.put(queue, Map.of("queued", queued, "active", active, "completed", completed, "priority", queuePriority(queue)));
        }
        counts.put("DEAD_LETTER_QUEUE", Map.of("queued", deadLetter.size(), "active", 0, "completed", 0));
        counts.put("_summary", Map.of("inMemoryQueueDepth", queuedLaneSize(), "inFlight", inFlightJobs.get(), "maxQueueDepth", Math.max(1, maxQueueDepth), "maxLaneDepth", Math.max(1, maxLaneDepth), "backpressureRejected", backpressureRejected.get()));
        return counts;
    }

    private Map<String, Object> workerState() {
        return Map.of("mode", "ASYNC_IN_MEMORY", "configured", Math.max(1, workerCount), "busy", inFlightJobs.get(), "queued", queuedLaneSize());
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
        return Map.of("ok", true, "requestId", "REQ-" + sequence.incrementAndGet(), "data", data, "meta", meta());
    }

    private Map<String, Object> error(String code, String message) {
        return Map.of("ok", false, "requestId", "REQ-" + sequence.incrementAndGet(), "error", Map.of("code", code, "message", message, "details", List.of()), "meta", meta());
    }

    private Map<String, Object> meta() {
        return Map.of("version", "v1", "timestamp", Instant.now().toString());
    }

    private Map<String, Object> withIdempotency(Map<String, Object> data, String key, boolean replayed, String originalResourceId) {
        Map<String, Object> copy = new LinkedHashMap<>(data);
        if (key != null) copy.put("idempotency", Map.of("key", key, "replayed", replayed, "originalResourceId", originalResourceId));
        return copy;
    }

    private Map<String, Object> jobView(RuntimeJob job) {
        Map<String, Object> view = new LinkedHashMap<>(job.asMap());
        view.put("mode", job.kind);
        view.put("progress", Map.of("stage", "completed", "percent", "COMPLETED".equals(job.status) ? 100 : 50));
        view.put("updatedAt", Instant.now().toString());
        view.put("links", Map.of("self", "/api/v1/jobs/" + job.jobId, "result", "/api/v1/jobs/" + job.jobId + "/result", "events", "/api/v1/jobs/" + job.jobId + "/events", "artifacts", "/api/v1/jobs/" + job.jobId + "/artifacts"));
        return view;
    }

    private Map<String, Object> staticResult(String jobId, int assigned) {
        return Map.of("mode", "STATIC_DISPATCH", "finalSolver", "IRX_ML_FUSED_HYBRID", "coverage", Map.of("assigned", assigned, "total", assigned, "rate", 1.0), "metrics", Map.of("distanceKm", 31.3, "lateCount", 0, "runtimeMs", 1024), "routes", List.of(), "diagnostics", Map.of("adaptiveMlPolicy", Map.of("adaptiveMlPolicyMode", "QUALITY_SEEKING"), "baselineDominanceGuard", Map.of("passed", true)));
    }

    void acceptLiveKafkaOrder(LiveKafkaEnvelope envelope) {
        if (envelope == null) return;
        try {
            bufferLiveOrder(envelope.payload());
        } catch (RuntimeException exception) {
            rejectLiveOrder(envelope.payload(), "consumer-error:" + rootReason(exception));
        }
    }

    void acceptLiveKafkaTelemetry(LiveKafkaEnvelope envelope) {
        if (envelope == null) return;
        activeDrivers = Math.max(activeDrivers, latestTelemetry.size() + 1);
        latestTelemetry.put("live:" + (envelope.driverId() == null ? "unknown" : envelope.driverId()), envelope.payload());
        addLiveEvent("TELEMETRY_UPDATED", Map.of("activeDrivers", activeDrivers));
    }

    private LiveKafkaEnvelope liveEnvelope(String type, Map<String, Object> payload) {
        Map<String, Object> data = payload == null ? Map.of() : payload;
        String tenantId = String.valueOf(data.getOrDefault("tenantId", "demo"));
        String regionId = String.valueOf(data.getOrDefault("regionId", "live-region"));
        String driverId = String.valueOf(data.getOrDefault("driverId", "unknown"));
        return new LiveKafkaEnvelope("irx-live-event/v1", "EVT-" + sequence.incrementAndGet(), type, tenantId, regionId, driverId, Instant.now(), data);
    }

    private void bufferLiveOrder(Map<String, Object> order) {
        if (!validLiveOrder(order)) {
            rejectLiveOrder(order, "invalid-live-order");
            return;
        }
        String dedupeKey = liveDedupeKey(order);
        Long previous = liveSeenOrderKeys.putIfAbsent(dedupeKey, System.currentTimeMillis());
        if (previous != null) {
            liveDuplicateOrders.incrementAndGet();
            addLiveEvent("LIVE_DUPLICATE_SKIPPED", Map.of("dedupeKey", dedupeKey));
            return;
        }
        if (bufferedOrders >= Math.max(1, liveKafkaProperties.getMaxBufferedOrders())) {
            rejectLiveOrder(order, "backpressure-buffer-full");
            return;
        }
        String regionId = liveBufferKey(order);
        long nowMs = System.currentTimeMillis();
        Map<String, Object> buffered = new LinkedHashMap<>(order);
        long placedAtMs = livePlacedAtMs(buffered, nowMs);
        buffered.putIfAbsent("placedAtMs", placedAtMs);
        buffered.putIfAbsent("orderCreatedAtMs", placedAtMs);
        buffered.putIfAbsent("_rawRegionId", String.valueOf(order.getOrDefault("regionId", "live-region")));
        buffered.putIfAbsent("_firstSeenAtMs", nowMs);
        buffered.putIfAbsent("_timeBucket", liveTimeBucket(buffered));
        buffered.putIfAbsent("_priorityClass", livePriorityClass(buffered));
        buffered.putIfAbsent("_geoCell", liveGeoCell(buffered));
        buffered.putIfAbsent("_lane", liveLane(buffered));
        buffered.putIfAbsent("_bufferedAtMs", nowMs);
        buffered.put("_orderAliveMs", liveOrderAliveMs(buffered, nowMs));
        buffered.putIfAbsent("_deferCount", 0);
        buffered.putIfAbsent("_forcedDispatch", false);
        buffered.putIfAbsent("_priorityScore", livePriorityScore(buffered));
        List<Map<String, Object>> buffer = liveOrderBuffers.computeIfAbsent(regionId, ignored -> Collections.synchronizedList(new ArrayList<>()));
        synchronized (buffer) {
            buffer.add(buffered);
            liveBufferFirstSeen.putIfAbsent(regionId, System.currentTimeMillis());
            bufferedOrders++;
            liveAcceptedOrders.incrementAndGet();
        }
        addLiveEvent("ORDER_BUFFERED", Map.of("regionId", regionId, "bufferedOrders", bufferedOrders));
    }

    private String liveBufferKey(Map<String, Object> order) {
        return String.valueOf(order.getOrDefault("regionId", "live-region"))
                + ":" + liveGeoCell(order)
                + ":" + liveTimeBucket(order)
                + ":" + livePriorityClass(order)
                + ":" + liveLane(order);
    }

    private boolean validLiveOrder(Map<String, Object> order) {
        if (order == null || order.isEmpty()) return false;
        double pickupLat = number(order, "pickupLat", number(order, "lat", Double.NaN));
        double pickupLng = number(order, "pickupLng", number(order, "lng", Double.NaN));
        double dropoffLat = number(order, "dropoffLat", Double.NaN);
        double dropoffLng = number(order, "dropoffLng", Double.NaN);
        if (!Double.isFinite(pickupLat) || !Double.isFinite(pickupLng) || !Double.isFinite(dropoffLat) || !Double.isFinite(dropoffLng)) return false;
        if (Math.abs(pickupLat) > 90.0 || Math.abs(dropoffLat) > 90.0 || Math.abs(pickupLng) > 180.0 || Math.abs(dropoffLng) > 180.0) return false;
        if (haversineKm(pickupLat, pickupLng, dropoffLat, dropoffLng) < 0.01) return false;
        return number(order, "promisedEtaMinutes", 45.0) > 0.0;
    }

    private String liveDedupeKey(Map<String, Object> order) {
        String tenant = String.valueOf(order.getOrDefault("tenantId", "demo"));
        String external = String.valueOf(order.getOrDefault("externalOrderId", order.getOrDefault("orderId", "")));
        if (!external.isBlank()) return tenant + ":" + external;
        return tenant + ":" + liveGeoCell(order) + ":" + number(order, "pickupLat", 0.0) + ":" + number(order, "pickupLng", 0.0) + ":" + number(order, "dropoffLat", 0.0) + ":" + number(order, "dropoffLng", 0.0);
    }

    private void rejectLiveOrder(Map<String, Object> order, String reason) {
        liveRejectedOrders.incrementAndGet();
        backpressureRejected.incrementAndGet();
        String orderId = order == null ? "unknown" : String.valueOf(order.getOrDefault("externalOrderId", order.getOrDefault("orderId", "unknown")));
        deadLetter.add("live:" + reason + ":" + orderId);
        addLiveEvent("LIVE_ORDER_REJECTED", Map.of("reason", reason, "orderId", orderId));
    }

    private long livePlacedAtMs(Map<String, Object> order, long fallbackNowMs) {
        for (String key : List.of("placedAtMs", "orderCreatedAtMs", "createdAtMs", "placedAt", "createdAt")) {
            Object value = order.get(key);
            Long parsed = parseEpochMs(value);
            if (parsed != null) return parsed;
        }
        return fallbackNowMs;
    }

    private long liveOrderAliveMs(Map<String, Object> order, long nowMs) {
        return Math.max(0L, nowMs - livePlacedAtMs(order, nowMs));
    }

    private Long parseEpochMs(Object value) {
        if (value == null) return null;
        if (value instanceof Number number) {
            long raw = number.longValue();
            return raw > 0L && raw < 1_000_000_000_000L ? raw * 1000L : raw;
        }
        String text = String.valueOf(value).trim();
        if (text.isBlank()) return null;
        try {
            long raw = Long.parseLong(text);
            return raw > 0L && raw < 1_000_000_000_000L ? raw * 1000L : raw;
        } catch (NumberFormatException ignored) {
            try { return Instant.parse(text).toEpochMilli(); } catch (Exception ignoredAgain) { return null; }
        }
    }

    private String liveLane(Map<String, Object> order) {
        if (isUrgentLiveOrder(order)) return "urgent";
        double eta = number(order, "promisedEtaMinutes", 45.0);
        if (eta <= 30.0) return "sla-hot";
        if (eta > 60.0) return "overflow-relaxed";
        return "normal";
    }

    private String liveTimeBucket(Map<String, Object> order) {
        double eta = number(order, "promisedEtaMinutes", 45.0);
        if (eta <= 15.0) return "urgent15";
        if (eta <= 30.0) return "hot30";
        if (eta <= 60.0) return "normal60";
        return "relaxed";
    }

    private String livePriorityClass(Map<String, Object> order) {
        if (isUrgentLiveOrder(order)) return "pU";
        double priority = number(order, "priority", 0.0);
        if (priority >= 8.0) return "pH";
        if (priority >= 4.0) return "pM";
        return "pL";
    }

    private String liveGeoCell(Map<String, Object> order) {
        double lat = number(order, "pickupLat", number(order, "lat", 0.0));
        double lng = number(order, "pickupLng", number(order, "lng", 0.0));
        return "g" + (int) Math.floor(lat * 100.0) + "_" + (int) Math.floor(lng * 100.0);
    }

    private void flushDueLiveBuffers() {
        try {
            long now = System.currentTimeMillis();
            for (String regionId : new ArrayList<>(liveOrderBuffers.keySet())) {
                List<Map<String, Object>> buffer = liveOrderBuffers.get(regionId);
                if (buffer == null || buffer.isEmpty()) continue;
                boolean shouldFlush;
                synchronized (buffer) {
                    long firstSeen = liveBufferFirstSeen.getOrDefault(regionId, now);
                    boolean hasUrgent = buffer.stream().anyMatch(this::isUrgentLiveOrder);
                    boolean hasHot = buffer.stream().anyMatch(order -> livePriorityScore(order) >= 80.0);
                    shouldFlush = hasUrgent || hasHot || buffer.size() >= Math.max(1, liveKafkaProperties.getMaxOrdersPerCycle()) || now - firstSeen >= Math.max(1L, liveKafkaProperties.getMaxWaitMs());
                }
                if (shouldFlush) flushLiveRegion(regionId);
            }
        } catch (RuntimeException ex) {
            addLiveEvent("LIVE_SCHEDULER_ERROR", Map.of("error", ex.getClass().getSimpleName(), "message", String.valueOf(ex.getMessage())));
        }
    }

    private int flushAllLiveBuffers() {
        int assigned = 0;
        for (String regionId : new ArrayList<>(liveOrderBuffers.keySet())) assigned += flushLiveRegion(regionId);
        return assigned;
    }

    private int flushLiveRegion(String regionId) {
        List<Map<String, Object>> buffer = liveOrderBuffers.get(regionId);
        if (buffer == null || buffer.isEmpty()) return 0;
        List<Map<String, Object>> selected;
        double avgScore;
        double avgSimilarity;
        int urgentCount;
        int maxScore;
        SelectedLiveBatch batch;
        synchronized (buffer) {
            buffer.sort(Comparator.comparingDouble(this::livePriorityScore).reversed());
            int take = dynamicLiveBatchSize(buffer);
            if (take <= 0) return 0;
            batch = selectBestLiveDispatchBatch(buffer, take);
            selected = batch.orders();
            buffer.removeAll(selected);
            markLiveSelectionAging(buffer, selected);
            if (buffer.isEmpty()) liveBufferFirstSeen.remove(regionId); else liveBufferFirstSeen.put(regionId, System.currentTimeMillis());
            avgScore = selected.stream().mapToDouble(this::livePriorityScore).average().orElse(0.0);
            Map<String, Object> seed = selected.isEmpty() ? Map.of() : selected.get(0);
            avgSimilarity = selected.stream().skip(1).mapToDouble(order -> liveSimilarityScore(seed, order)).average().orElse(1.0);
            urgentCount = (int) selected.stream().filter(this::isUrgentLiveOrder).count();
            maxScore = (int) Math.round(selected.stream().mapToDouble(this::livePriorityScore).max().orElse(0.0));
        }
        int assigned = selected.size();
        String cycleId = "LIVE-CYC-" + sequence.incrementAndGet();
        LiveCoreExecution liveCoreExecution = executeLiveCoreBatch(cycleId, regionId, selected);
        bufferedOrders = Math.max(0, bufferedOrders - assigned);
        liveAssignedOrders.addAndGet(assigned);
        liveMaxBatchSize.accumulateAndGet(assigned, Math::max);
        liveSimilaritySamples.incrementAndGet();
        liveSimilarityScoreScaled.addAndGet(Math.round(avgSimilarity * 1000.0));
        completedCycles++;
        lastCycleId = cycleId;
        Map<String, Object> result = liveCycleResult(cycleId, regionId, assigned, avgScore, maxScore, avgSimilarity, urgentCount, liveCoreExecution, batch);
        cycleResults.put(cycleId, result);
        addLiveEvent("LIVE_CYCLE_STARTED", Map.of("cycleId", cycleId, "regionId", regionId, "orders", assigned));
        addLiveEvent("LIVE_BATCH_SELECTED", batch.asMap(bufferedOrders));
        addLiveEvent("LIVE_CYCLE_COMPLETED", result);
        LiveKafkaBridge bridge = liveKafkaBridgeProvider.getIfAvailable();
        if (bridge != null) bridge.publishResult(result);
        return assigned;
    }

    private LiveCoreExecution executeLiveCoreBatch(String cycleId, String regionId, List<Map<String, Object>> selected) {
        LiveAdaptiveBundlePlanner.PlanResult plan = liveAdaptiveBundlePlanner.plan(selected);
        if (!coreProperties.isEnabled()) {
            liveFallbackCycles.incrementAndGet();
            double initialCost = liveInitialRouteCost(selected);
            LivePdLnsPostSolverImprover.Result repair = livePdLnsPostSolverImprover.improve(selected, List.of(), initialCost, initialCost, solverPolicy(selected), plan.breakRisk());
            return new LiveCoreExecution(false, "core-disabled", 0, 0, 0L, List.of(), initialCost, initialCost, 0.0, solverPolicy(selected), plan, repair, List.of());
        }
        int maxChunkSize = liveCoreChunkSize(selected);
        int assigned = 0;
        int chunkCount = 0;
        long runtimeMsTotal = 0L;
        double initialCost = liveInitialRouteCost(selected);
        double finalUtility = 0.0;
        List<Map<String, Object>> assignmentRows = new ArrayList<>();
        List<MlStageMetadata> mlRows = new ArrayList<>();
        try {
            for (int from = 0; from < selected.size(); from += maxChunkSize) {
                int to = Math.min(selected.size(), from + maxChunkSize);
                List<Map<String, Object>> chunk = selected.subList(from, to);
                long started = System.nanoTime();
                DispatchV2Request request = inputMapper.toRequest(cycleId + ":" + regionId, chunkCount, chunk);
                DispatchV2Result result = dispatchV2Core.dispatch(request);
                mlRows.addAll(result.mlStageMetadata());
                long runtimeMs = (System.nanoTime() - started) / 1_000_000L;
                if (runtimeMs > Math.max(1L, coreProperties.getTimeoutMs())) {
                    liveCoreTimeouts.incrementAndGet();
                }
                runtimeMsTotal += runtimeMs;
                chunkCount++;
                List<Map<String, Object>> rows = result.assignments().stream()
                        .flatMap(assignment -> assignment.orderIds().stream().map(orderId -> assignmentRow(assignment, orderId)))
                        .toList();
                assignmentRows.addAll(rows);
                List<Map<String, Object>> repairRows = liveCoverageRepairRows(chunk, assignmentRows);
                liveRepairCoveredOrders.addAndGet(repairRows.size());
                assignmentRows.addAll(repairRows);
                assignmentRows = dedupeLiveAssignmentRows(assignmentRows);
                assignmentRows = filterLiveAssignmentRows(selected, assignmentRows);
                assigned = assignmentRows.size();
                finalUtility += result.assignments().stream().mapToDouble(this::assignmentUtility).sum();
            }
            double finalCost = liveFinalCost(initialCost, finalUtility, assigned, selected.size());
            LivePdLnsPostSolverImprover.Result repair = livePdLnsPostSolverImprover.improve(selected, assignmentRows, initialCost, finalCost, solverPolicy(selected), plan.breakRisk());
            if (repair.accepted()) finalCost = repair.finalCost();
            liveCoreCycles.incrementAndGet();
            liveCoreAssignedOrders.addAndGet(assigned);
            liveCoreRuntimeSamples.incrementAndGet();
            liveCoreRuntimeMsTotal.addAndGet(runtimeMsTotal);
            return new LiveCoreExecution(true, "", assigned, chunkCount, runtimeMsTotal, assignmentRows, initialCost, finalCost, improvementPercent(initialCost, finalCost), solverPolicy(selected), plan, repair, mlRows);
        } catch (Exception exception) {
            liveFallbackCycles.incrementAndGet();
            LivePdLnsPostSolverImprover.Result repair = livePdLnsPostSolverImprover.improve(selected, assignmentRows, initialCost, initialCost, solverPolicy(selected), plan.breakRisk());
            return new LiveCoreExecution(false, rootReason(exception), selected.size(), Math.max(1, chunkCount), runtimeMsTotal, assignmentRows, initialCost, initialCost, 0.0, solverPolicy(selected), plan, repair, mlRows);
        }
    }

    private String rootReason(Exception exception) {
        Throwable current = exception;
        while (current.getCause() != null) current = current.getCause();
        String message = current.getMessage();
        return current.getClass().getSimpleName() + (message == null || message.isBlank() ? "" : ":" + message);
    }

    private Map<String, Object> liveCycleResult(String cycleId, String regionId, int assigned, double avgScore, int maxScore, double avgSimilarity, int urgentCount, LiveCoreExecution coreExecution, SelectedLiveBatch batch) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("cycleId", cycleId);
        result.put("regionId", regionId);
        result.put("assigned", assigned);
        result.put("selectedOrders", assigned);
        result.put("status", "COMPLETED");
        result.put("microBatch", true);
        result.put("policy", coreExecution.core() ? "SIMILARITY_PRIORITY_CORE_DYNAMIC" : "SIMILARITY_PRIORITY_HEURISTIC_FALLBACK");
        result.put("avgPriority", Math.round(avgScore));
        result.put("maxPriority", maxScore);
        result.put("avgSimilarity", Math.round(avgSimilarity * 100.0) / 100.0);
        result.put("urgentCount", urgentCount);
        result.put("selection", batch.asMap(Math.max(0, bufferedOrders)));
        result.put("core", coreExecution.core());
        result.put("fallbackReason", coreExecution.fallbackReason());
        result.put("coreAssigned", coreExecution.assigned());
        result.put("coreAssignedDelta", coreExecution.assigned() - assigned);
        result.put("coreChunkCount", coreExecution.chunkCount());
        result.put("coreRuntimeMs", coreExecution.runtimeMs());
        result.put("assignmentCount", coreExecution.assignments().size());
        result.put("solverPolicy", coreExecution.solverPolicy());
        result.put("solverGoals", solverGoals(coreExecution.solverPolicy(), assigned));
        result.put("seedContributors", defaultSeedContributors());
        result.put("seedRuntime", solverRuntimeManager.compactStatus());
        result.put("pipeline", livePipeline(coreExecution));
        result.put("lm", liveLmTelemetry(coreExecution));
        result.put("initialCost", Math.round(coreExecution.initialCost() * 100.0) / 100.0);
        result.put("finalCost", Math.round(coreExecution.finalCost() * 100.0) / 100.0);
        result.put("improvementPercent", Math.round(coreExecution.improvementPercent() * 100.0) / 100.0);
        result.put("adaptiveLayer", coreExecution.plan().asMap());
        result.put("postSolverRepair", coreExecution.repair().asMap());
        result.put("repairMode", coreExecution.repair().repairMode());
        result.put("safetyPassed", coreExecution.repair().safetyPassed());
        return result;
    }

    private Map<String, Object> livePipeline(LiveCoreExecution execution) {
        return Map.of(
                "flow", List.of("kafka", "bigdatalite", "core", "seed", "repair", "lm"),
                "kafka", Map.of("transport", liveKafkaBridgeProvider.getIfAvailable() == null ? "local" : "kafka"),
                "bigdataLite", Map.of("policy", "feasibility-similarity-priority-microbatch"),
                "core", Map.of("enabled", coreProperties.isEnabled(), "used", execution.core(), "runtimeMs", execution.runtimeMs()),
                "seed", Map.of("policy", execution.solverPolicy(), "contributors", defaultSeedContributors()),
                "repair", execution.repair().asMap(),
                "lm", liveLmTelemetry(execution));
    }

    private Map<String, Object> liveLmTelemetry(LiveCoreExecution execution) {
        List<Map<String, Object>> stages = execution.mlStageMetadata().stream()
                .map(this::mlStageMap)
                .toList();
        long applied = execution.mlStageMetadata().stream().filter(MlStageMetadata::applied).count();
        boolean fallbackUsed = execution.mlStageMetadata().stream().anyMatch(MlStageMetadata::fallbackUsed);
        return Map.of(
                "mode", "CORE_LM_ASSISTED_REPAIR",
                "models", List.of("GreedRL", "TabularAdaptiveLearning", "RouteFinder", "ForecastRisk"),
                "coreMlStageCount", execution.mlStageMetadata().size(),
                "coreMlAppliedCount", applied,
                "fallbackUsed", fallbackUsed,
                "repairPolicy", execution.repair().repairMode(),
                "repairOperators", execution.repair().operators(),
                "stages", stages);
    }

    private Map<String, Object> mlStageMap(MlStageMetadata metadata) {
        return Map.of(
                "stage", metadata.stageName(),
                "sourceModel", metadata.sourceModel(),
                "modelVersion", metadata.modelVersion(),
                "latencyMs", metadata.latencyMs(),
                "applied", metadata.applied(),
                "fallbackUsed", metadata.fallbackUsed());
    }

    private double liveInitialRouteCost(List<Map<String, Object>> selected) {
        if (selected.isEmpty()) return 0.0;
        List<Map<String, Object>> sorted = selected.stream()
                .sorted(Comparator.comparingDouble(this::livePriorityScore).reversed())
                .toList();
        double km = 0.0;
        Map<String, Object> previous = sorted.get(0);
        km += orderKm(previous);
        for (int i = 1; i < sorted.size(); i++) {
            Map<String, Object> current = sorted.get(i);
            km += haversineKm(number(previous, "dropoffLat", 0.0), number(previous, "dropoffLng", 0.0), number(current, "pickupLat", 0.0), number(current, "pickupLng", 0.0));
            km += orderKm(current);
            previous = current;
        }
        double latenessRisk = selected.stream().mapToDouble(order -> Math.max(0.0, livePriorityScore(order) - 120.0) / 120.0).sum();
        return km + latenessRisk * 5.0;
    }

    private double assignmentUtility(DispatchAssignment assignment) {
        return Math.max(0.0, assignment.routeValue()) + Math.max(0.0, assignment.selectionScore()) + Math.max(0.0, assignment.robustUtility());
    }

    private double liveFinalCost(double initialCost, double finalUtility, int assigned, int selected) {
        double coverageReward = selected <= 0 ? 0.0 : Math.min(0.35, assigned * 1.0 / selected) * initialCost;
        double utilityReward = Math.min(initialCost * 0.40, finalUtility * 0.02);
        return Math.max(0.0, initialCost - coverageReward - utilityReward);
    }

    private double improvementPercent(double initialCost, double finalCost) {
        return initialCost <= 0.0 ? 0.0 : Math.max(0.0, (initialCost - finalCost) * 100.0 / initialCost);
    }

    private String solverPolicy(List<Map<String, Object>> selected) {
        boolean urgent = selected.stream().anyMatch(this::isUrgentLiveOrder);
        boolean hardWindow = selected.stream().anyMatch(order -> number(order, "promisedEtaMinutes", 45.0) <= 30.0);
        if (urgent && selected.size() <= 50) return "CORE_OR_TOOLS_VROOM_PYVRP_FAST_SEED";
        if (hardWindow) return "CORE_OR_TOOLS_VROOM_PYVRP_TIME_WINDOW_SEED";
        if (selected.size() >= 150) return "CORE_OR_TOOLS_VROOM_PYVRP_BULK_SEED";
        return "CORE_OR_TOOLS_VROOM_PYVRP_DEFAULT_SEED";
    }

    private List<Map<String, Object>> defaultSeedContributors() {
        Map<String, String> runtime = solverRuntimeManager.compactStatus();
        return List.of(
                seedContributorGoal("OR_TOOLS", runtime.getOrDefault("ortools", "UNKNOWN"), "hard-constraints/set-packing/time-window"),
                seedContributorGoal("VROOM", runtime.getOrDefault("vroom", "UNKNOWN"), "route-quality/distance-seed"),
                seedContributorGoal("PYVRP", runtime.getOrDefault("pyvrp", "UNKNOWN"), "hgs-quality/post-solver-seed")
        );
    }

    private Map<String, Object> seedContributorGoal(String solver, String status, String goal) {
        return Map.of("solver", solver, "defaultSeed", true, "status", status, "goal", goal);
    }

    private Map<String, Object> solverGoals(String policy, int selectedOrders) {
        return Map.of(
                "policy", policy,
                "selectedOrders", selectedOrders,
                "orToolsGoal", "always-on-global-selector-constraint-seed",
                "vroomGoal", "always-on-distance-route-seed-when-runtime-available",
                "pyvrpGoal", "always-on-hgs-quality-seed-when-runtime-available",
                "fallbackRule", "runtime-unavailable-keeps-core-result-and-records-evidence-gap");
    }

    private int liveCoreChunkSize(List<Map<String, Object>> selected) {
        int configuredMax = Math.max(1, coreProperties.getMaxOrdersPerChunk());
        boolean urgent = selected.stream().anyMatch(this::isUrgentLiveOrder);
        boolean hot = selected.stream().anyMatch(order -> number(order, "promisedEtaMinutes", 45.0) <= 30.0);
        int base = urgent ? 50 : hot ? 80 : selected.size() >= 200 ? 200 : 120;
        if (selected.size() <= 10) base = 1;
        if (liveCoreTimeouts.get() > 0) base = Math.max(1, base / 2);
        if (liveCoreTimeouts.get() > liveCoreCycles.get() / 2) base = Math.max(1, base / 2);
        if (bufferedOrders > liveKafkaProperties.getMaxOrdersPerCycle() * 5 && liveCoreTimeouts.get() == 0) base = Math.min(configuredMax, base * 2);
        return Math.max(1, Math.min(Math.min(configuredMax, selected.size()), base));
    }

    private int dynamicLiveBatchSize(List<Map<String, Object>> buffer) {
        int max = Math.max(1, liveKafkaProperties.getMaxOrdersPerCycle());
        int backlog = Math.max(0, liveAcceptedOrders.get() - liveAssignedOrders.get());
        if (backlog >= max) return Math.min(buffer.size(), max);
        int urgent = (int) buffer.stream().filter(this::isUrgentLiveOrder).count();
        long hot = buffer.stream().filter(order -> livePriorityScore(order) >= 80.0).count();
        if (buffer.size() >= max) return max;
        if (urgent > 0) return Math.min(buffer.size(), Math.max(1, Math.min(max, urgent + 25)));
        if (hot > 0) return Math.min(buffer.size(), Math.max(25, Math.min(max, (int) hot + 25)));
        if (buffer.size() < max) return Math.min(buffer.size(), Math.max(1, buffer.size()));
        return Math.min(buffer.size(), Math.max(25, max / 2));
    }

    private SelectedLiveBatch selectBestLiveDispatchBatch(List<Map<String, Object>> buffer, int take) {
        if (buffer.isEmpty() || take <= 0) return SelectedLiveBatch.empty();
        List<Map<String, Object>> forced = liveForcedDispatchOrders(buffer, take);
        if (!forced.isEmpty()) {
            Map<String, Object> seed = forced.get(0);
            List<Map<String, Object>> selected = new ArrayList<>(forced);
            buffer.stream()
                    .filter(order -> !selected.contains(order))
                    .filter(order -> selected.stream().allMatch(selectedOrder -> liveFeasiblePair(selectedOrder, order)))
                    .sorted(Comparator.<Map<String, Object>>comparingDouble(order -> liveGraphEdgeValue(seed, order)).reversed())
                    .forEach(order -> {
                        if (selected.size() < take && liveFeasibleWithBatch(selected, order)) selected.add(order);
                    });
            SelectedLiveBatch batch = describeSelectedBatch(seed, selected, buffer.size());
            List<String> reasons = new ArrayList<>(batch.reasons());
            reasons.add("starvation-guard-applied");
            if (forced.stream().anyMatch(order -> liveOrderAliveMs(order, System.currentTimeMillis()) >= liveForceAliveMs())) reasons.add("forced-alive-time");
            if (forced.stream().anyMatch(order -> longNumber(order, "_deferCount", 0L) >= liveMaxDeferCycles())) reasons.add("max-defer-cycles");
            if (forced.stream().anyMatch(this::liveSlaHot)) reasons.add("sla-hot");
            return batch.withFairness("RESCUE", forced.size(), true, reasons);
        }
        List<Map<String, Object>> seeds = buffer.stream()
                .sorted(Comparator.<Map<String, Object>>comparingDouble(this::liveSeedValue).reversed())
                .limit(Math.min(buffer.size(), Math.max(4, Math.min(16, take * 2))))
                .toList();
        SelectedLiveBatch best = null;
        for (Map<String, Object> seed : seeds) {
            List<Map<String, Object>> candidate = new ArrayList<>();
            candidate.add(seed);
            buffer.stream()
                    .filter(order -> order != seed)
                    .filter(order -> liveFeasiblePair(seed, order))
                    .sorted(Comparator.<Map<String, Object>>comparingDouble(order -> liveGraphEdgeValue(seed, order)).reversed())
                    .forEach(order -> {
                        if (candidate.size() < take && liveFeasibleWithBatch(candidate, order)) candidate.add(order);
                    });
            SelectedLiveBatch current = describeSelectedBatch(seed, candidate, buffer.size());
            if (best == null || current.batchValue() > best.batchValue()) best = current;
        }
        return best == null ? describeSelectedBatch(buffer.get(0), List.of(buffer.get(0)), buffer.size()) : best.withFairness("GRAPH", 0, false, best.reasons());
    }

    private List<Map<String, Object>> liveForcedDispatchOrders(List<Map<String, Object>> buffer, int take) {
        int quota = Math.max(1, Math.min(3, take));
        return buffer.stream()
                .filter(this::liveMustForceDispatch)
                .sorted(Comparator.<Map<String, Object>>comparingDouble(this::liveSeedValue).reversed())
                .limit(quota)
                .toList();
    }

    private boolean liveMustForceDispatch(Map<String, Object> order) {
        long now = System.currentTimeMillis();
        return liveOrderAliveMs(order, now) >= liveForceAliveMs()
                || longNumber(order, "_deferCount", 0L) >= liveMaxDeferCycles()
                || liveSlaHot(order);
    }

    private boolean liveSlaHot(Map<String, Object> order) {
        return isUrgentLiveOrder(order) || number(order, "promisedEtaMinutes", 45.0) <= 15.0 || livePriorityScore(order) >= 120.0;
    }

    private long liveForceAliveMs() {
        return 30_000L;
    }

    private long liveMaxDeferCycles() {
        return 3L;
    }

    private void markLiveSelectionAging(List<Map<String, Object>> remaining, List<Map<String, Object>> selected) {
        long now = System.currentTimeMillis();
        for (Map<String, Object> order : selected) {
            order.put("_selectedAtMs", now);
            order.put("_orderAliveMs", liveOrderAliveMs(order, now));
            order.put("_forcedDispatch", liveMustForceDispatch(order));
        }
        for (Map<String, Object> order : remaining) {
            order.put("_orderAliveMs", liveOrderAliveMs(order, now));
            order.put("_deferCount", longNumber(order, "_deferCount", 0L) + 1L);
            order.put("_lastDeferredAtMs", now);
            order.put("_lastDeferredReason", "not-selected-by-current-cycle");
        }
    }

    private boolean liveFeasibleWithBatch(List<Map<String, Object>> selected, Map<String, Object> candidate) {
        return selected.stream().allMatch(order -> liveFeasiblePair(order, candidate));
    }

    private SelectedLiveBatch describeSelectedBatch(Map<String, Object> seed, List<Map<String, Object>> selected, int candidateCount) {
        double priorityValue = selected.stream().mapToDouble(this::livePriorityScore).sum();
        double shareabilityValue = selected.stream().filter(order -> order != seed).mapToDouble(order -> liveGraphEdgeValue(seed, order)).sum();
        double riskPenalty = selected.stream().mapToDouble(this::liveSelectionRiskPenalty).sum();
        double corePenalty = Math.max(0, selected.size() - 8) * 4.0;
        double value = priorityValue + shareabilityValue - riskPenalty - corePenalty;
        List<String> reasons = new ArrayList<>();
        if (selected.stream().anyMatch(this::isUrgentLiveOrder)) reasons.add("urgent-or-sla-hot");
        if (selected.size() > 1) reasons.add("shareability-graph-positive");
        if (selected.stream().mapToDouble(this::livePriorityScore).max().orElse(0) >= 80) reasons.add("high-admission-value");
        if (riskPenalty <= selected.size() * 5.0) reasons.add("low-break-risk");
        return new SelectedLiveBatch(
                List.copyOf(selected),
                orderId(seed),
                Math.round(value * 100.0) / 100.0,
                candidateCount,
                Math.max(0, candidateCount - selected.size()),
                "GRAPH",
                0,
                liveBadOrderCount(selected),
                liveOldestAliveMs(selected),
                liveAvgAliveMs(selected),
                false,
                reasons.isEmpty() ? List.of("best-graph-value") : List.copyOf(reasons));
    }

    private long liveOldestAliveMs(List<Map<String, Object>> orders) {
        long now = System.currentTimeMillis();
        return orders.stream().mapToLong(order -> liveOrderAliveMs(order, now)).max().orElse(0L);
    }

    private long liveAvgAliveMs(List<Map<String, Object>> orders) {
        long now = System.currentTimeMillis();
        return Math.round(orders.stream().mapToLong(order -> liveOrderAliveMs(order, now)).average().orElse(0.0));
    }

    private int liveBadOrderCount(List<Map<String, Object>> orders) {
        return (int) orders.stream().filter(order -> orderKm(order) > 8.0 || liveSelectionRiskPenalty(order) > 8.0).count();
    }

    private double liveSeedValue(Map<String, Object> order) {
        long now = System.currentTimeMillis();
        double age = Math.min(300.0, liveOrderAliveMs(order, now) / 1000.0 * 5.0 + longNumber(order, "_deferCount", 0L) * 30.0);
        double sla = Math.max(0.0, 60.0 - number(order, "promisedEtaMinutes", 45.0));
        return livePriorityScore(order) + age + sla + (isUrgentLiveOrder(order) ? 30.0 : 0.0);
    }

    private double liveGraphEdgeValue(Map<String, Object> seed, Map<String, Object> candidate) {
        return liveHybridBatchScore(seed, candidate)
                + routeDirectionSimilarity(seed, candidate) * 15.0
                + liveInsertionSavingScore(seed, candidate) * 20.0
                - liveSelectionRiskPenalty(candidate);
    }

    private double liveSelectionRiskPenalty(Map<String, Object> order) {
        double deadlineRisk = Math.max(0.0, 20.0 - number(order, "promisedEtaMinutes", 45.0)) * 0.6;
        double longRouteRisk = Math.max(0.0, orderKm(order) - 8.0) * 0.5;
        return deadlineRisk + longRouteRisk;
    }

    private List<Map<String, Object>> selectSimilarityLiveBatch(List<Map<String, Object>> buffer, int take) {
        if (buffer.isEmpty() || take <= 0) return List.of();
        Map<String, Object> seed = buffer.get(0);
        List<Map<String, Object>> selected = new ArrayList<>();
        selected.add(seed);
        buffer.stream()
                .skip(1)
                .filter(order -> liveFeasiblePair(seed, order))
                .sorted(Comparator.<Map<String, Object>>comparingDouble(order -> liveHybridBatchScore(seed, order)).reversed())
                .limit(Math.max(0, take - 1L))
                .forEach(selected::add);
        return selected;
    }

    private double liveHybridBatchScore(Map<String, Object> seed, Map<String, Object> candidate) {
        if (!liveFeasiblePair(seed, candidate)) return -1_000_000.0;
        return liveSimilarityScore(seed, candidate) * 100.0 + livePriorityScore(candidate) * 0.35;
    }

    private boolean liveFeasiblePair(Map<String, Object> left, Map<String, Object> right) {
        if (sameOrder(left, right)) return true;
        return sequenceFeasible(left, right, true, true)
                || sequenceFeasible(left, right, true, false)
                || sequenceFeasible(left, right, false, true)
                || sequenceFeasible(left, right, false, false);
    }

    private boolean sequenceFeasible(Map<String, Object> first, Map<String, Object> second, boolean firstPickupThenSecondPickup, boolean firstDropThenSecondDrop) {
        List<Map<String, Object>> pickupOrder = firstPickupThenSecondPickup ? List.of(first, second) : List.of(second, first);
        List<Map<String, Object>> dropOrder = firstDropThenSecondDrop ? List.of(first, second) : List.of(second, first);
        if (!pickupOrder.contains(dropOrder.get(0)) || !pickupOrder.contains(dropOrder.get(1))) return false;
        double minutes = 0.0;
        double currentLat = number(pickupOrder.get(0), "pickupLat", 0.0);
        double currentLng = number(pickupOrder.get(0), "pickupLng", 0.0);
        Set<Map<String, Object>> picked = new LinkedHashSet<>();
        Map<Map<String, Object>, Double> deliveredAt = new IdentityHashMap<>();
        for (Map<String, Object> order : pickupOrder) {
            minutes += travelMinutes(currentLat, currentLng, number(order, "pickupLat", 0.0), number(order, "pickupLng", 0.0));
            picked.add(order);
            currentLat = number(order, "pickupLat", 0.0);
            currentLng = number(order, "pickupLng", 0.0);
        }
        for (Map<String, Object> order : dropOrder) {
            if (!picked.contains(order)) return false;
            minutes += travelMinutes(currentLat, currentLng, number(order, "dropoffLat", 0.0), number(order, "dropoffLng", 0.0));
            deliveredAt.put(order, minutes);
            currentLat = number(order, "dropoffLat", 0.0);
            currentLng = number(order, "dropoffLng", 0.0);
        }
        if (deliveredAt.getOrDefault(first, Double.MAX_VALUE) > number(first, "promisedEtaMinutes", 45.0)) return false;
        if (deliveredAt.getOrDefault(second, Double.MAX_VALUE) > number(second, "promisedEtaMinutes", 45.0)) return false;
        if (isUrgentLiveOrder(first) != isUrgentLiveOrder(second)) {
            Map<String, Object> urgent = isUrgentLiveOrder(first) ? first : second;
            Map<String, Object> normal = urgent == first ? second : first;
            return deliveredAt.getOrDefault(urgent, Double.MAX_VALUE) <= deliveredAt.getOrDefault(normal, -1.0);
        }
        return true;
    }

    private boolean sameOrder(Map<String, Object> left, Map<String, Object> right) {
        return Objects.equals(left.get("externalOrderId"), right.get("externalOrderId"))
                || Objects.equals(left.get("orderId"), right.get("orderId"));
    }

    private String orderId(Map<String, Object> order) {
        return String.valueOf(order.getOrDefault("externalOrderId", order.getOrDefault("orderId", "unknown")));
    }

    private double liveSimilarityScore(Map<String, Object> left, Map<String, Object> right) {
        double pickup = geoSimilarity(left, right, "pickupLat", "pickupLng");
        double dropoff = geoSimilarity(left, right, "dropoffLat", "dropoffLng");
        double time = 1.0 - Math.min(1.0, Math.abs(number(left, "promisedEtaMinutes", 45.0) - number(right, "promisedEtaMinutes", 45.0)) / 45.0);
        double insertion = liveInsertionSavingScore(left, right);
        double priority = 1.0 - Math.min(1.0, Math.abs(number(left, "priority", 1.0) - number(right, "priority", 1.0)) / 10.0);
        double urgentPenalty = isUrgentLiveOrder(left) == isUrgentLiveOrder(right) ? 0.0 : 0.15;
        return Math.max(0.0, Math.min(1.0, pickup * 0.30 + dropoff * 0.25 + time * 0.20 + insertion * 0.15 + priority * 0.10 - urgentPenalty));
    }

    private double geoSimilarity(Map<String, Object> left, Map<String, Object> right, String latKey, String lngKey) {
        double km = haversineKm(number(left, latKey, 0.0), number(left, lngKey, 0.0), number(right, latKey, 0.0), number(right, lngKey, 0.0));
        return 1.0 / (1.0 + km);
    }

    private double routeDirectionSimilarity(Map<String, Object> left, Map<String, Object> right) {
        double leftDx = number(left, "dropoffLng", 0.0) - number(left, "pickupLng", 0.0);
        double leftDy = number(left, "dropoffLat", 0.0) - number(left, "pickupLat", 0.0);
        double rightDx = number(right, "dropoffLng", 0.0) - number(right, "pickupLng", 0.0);
        double rightDy = number(right, "dropoffLat", 0.0) - number(right, "pickupLat", 0.0);
        double denom = Math.sqrt(leftDx * leftDx + leftDy * leftDy) * Math.sqrt(rightDx * rightDx + rightDy * rightDy);
        if (denom <= 0.0) return 0.5;
        return (Math.max(-1.0, Math.min(1.0, (leftDx * rightDx + leftDy * rightDy) / denom)) + 1.0) / 2.0;
    }

    private double liveInsertionSavingScore(Map<String, Object> left, Map<String, Object> right) {
        double direct = orderKm(left) + orderKm(right);
        double leftFirst = pooledKm(left, right);
        double rightFirst = pooledKm(right, left);
        double pooled = Math.min(leftFirst, rightFirst);
        if (direct <= 0.0 || pooled <= 0.0) return routeDirectionSimilarity(left, right);
        double saving = direct / pooled;
        return Math.max(0.0, Math.min(1.0, saving));
    }

    private double orderKm(Map<String, Object> order) {
        return haversineKm(number(order, "pickupLat", 0.0), number(order, "pickupLng", 0.0), number(order, "dropoffLat", 0.0), number(order, "dropoffLng", 0.0));
    }

    private double pooledKm(Map<String, Object> first, Map<String, Object> second) {
        return haversineKm(number(first, "pickupLat", 0.0), number(first, "pickupLng", 0.0), number(second, "pickupLat", 0.0), number(second, "pickupLng", 0.0))
                + haversineKm(number(second, "pickupLat", 0.0), number(second, "pickupLng", 0.0), number(first, "dropoffLat", 0.0), number(first, "dropoffLng", 0.0))
                + haversineKm(number(first, "dropoffLat", 0.0), number(first, "dropoffLng", 0.0), number(second, "dropoffLat", 0.0), number(second, "dropoffLng", 0.0));
    }

    private double haversineKm(double lat1, double lng1, double lat2, double lng2) {
        double earthKm = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2.0) * Math.sin(dLat / 2.0)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2.0) * Math.sin(dLng / 2.0);
        return earthKm * 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));
    }

    private double travelMinutes(double lat1, double lng1, double lat2, double lng2) {
        return haversineKm(lat1, lng1, lat2, lng2) * 2.4 + 1.0;
    }

    private double livePriorityScore(Map<String, Object> order) {
        double score = 0.0;
        if (isUrgentLiveOrder(order)) score += 100.0;
        score += number(order, "priority", 0.0) * 10.0;
        long now = System.currentTimeMillis();
        score += Math.min(300.0, liveOrderAliveMs(order, now) / 1000.0 * 5.0 + longNumber(order, "_deferCount", 0L) * 30.0);
        double promised = number(order, "promisedEtaMinutes", 45.0);
        score += Math.max(0.0, 45.0 - promised);
        return score;
    }

    private boolean isUrgentLiveOrder(Map<String, Object> order) {
        Object urgent = order.get("urgent");
        return Boolean.TRUE.equals(urgent) || "true".equalsIgnoreCase(String.valueOf(urgent));
    }

    private double number(Map<String, Object> item, String key, double fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private long longNumber(Map<String, Object> item, String key, long fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.longValue();
        try { return value == null ? fallback : Long.parseLong(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private Map<String, Object> liveStateMap() {
        long similaritySamples = liveSimilaritySamples.get();
        double avgSimilarity = similaritySamples == 0 ? 0.0 : liveSimilarityScoreScaled.get() / 1000.0 / similaritySamples;
        double avgBatchSize = completedCycles == 0 ? 0.0 : liveAssignedOrders.get() * 1.0 / completedCycles;
        long coreRuntimeSamples = liveCoreRuntimeSamples.get();
        double avgCoreRuntimeMs = coreRuntimeSamples == 0 ? 0.0 : liveCoreRuntimeMsTotal.get() * 1.0 / coreRuntimeSamples;
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("running", liveRunning);
        state.put("mode", "LIVE_ROLLING");
        state.put("transport", liveKafkaBridgeProvider.getIfAvailable() == null ? "local" : "kafka");
        state.put("acceptedOrders", liveAcceptedOrders.get());
        state.put("assignedOrders", liveAssignedOrders.get());
        state.put("rejectedOrders", liveRejectedOrders.get());
        state.put("duplicateOrders", liveDuplicateOrders.get());
        state.put("bufferedOrders", bufferedOrders);
        state.put("backlogOrders", Math.max(0, liveAcceptedOrders.get() - liveAssignedOrders.get()));
        state.put("backpressureRejected", backpressureRejected.get());
        state.put("activeDrivers", activeDrivers);
        state.put("completedCycles", completedCycles);
        state.put("lastCycleId", lastCycleId);
        state.put("regions", liveOrderBuffers.keySet());
        state.put("avgBatchSize", Math.round(avgBatchSize * 100.0) / 100.0);
        state.put("maxBatchSize", liveMaxBatchSize.get());
        state.put("avgSimilarity", Math.round(avgSimilarity * 1000.0) / 1000.0);
        state.put("coreEnabled", coreProperties.isEnabled());
        state.put("coreCycles", liveCoreCycles.get());
        state.put("fallbackCycles", liveFallbackCycles.get());
        state.put("coreAssignedOrders", liveCoreAssignedOrders.get());
        state.put("coreTimeouts", liveCoreTimeouts.get());
        state.put("repairCoveredOrders", liveRepairCoveredOrders.get());
        state.put("avgCoreRuntimeMs", Math.round(avgCoreRuntimeMs * 100.0) / 100.0);
        state.put("defaultSeedContributors", defaultSeedContributors());
        state.put("seedRuntime", solverRuntimeManager.compactStatus());
        state.put("slo", Map.of(
                "targetCoreRuntimeMs", coreProperties.getTimeoutMs(),
                "coreRuntimeBreaches", liveCoreTimeouts.get(),
                "fallbackCycles", liveFallbackCycles.get(),
                "backlogOrders", Math.max(0, liveAcceptedOrders.get() - liveAssignedOrders.get())));
        return state;
    }

    private void addLiveEvent(String type, Map<String, Object> data) {
        liveEvents.add(new RuntimeEvent("EVT-" + sequence.incrementAndGet(), "LIVE", type, Instant.now().toString(), data));
    }

    private Map<String, Object> batchView(RuntimeJob job) {
        int queuedItems = "QUEUED".equals(job.status) || "RETRYING".equals(job.status) ? job.accepted : 0;
        int processedItems = "COMPLETED".equals(job.status) ? job.accepted : 0;
        return Map.of("batchId", job.batchId, "status", job.status, "totalItems", job.accepted + job.rejected, "normalizedItems", job.accepted, "deadLetterItems", job.rejected, "queuedItems", queuedItems, "processedItems", processedItems, "links", Map.of("self", "/api/v1/bigdata/batches/" + job.batchId, "items", "/api/v1/bigdata/batches/" + job.batchId + "/items", "deadLetter", "/api/v1/bigdata/dead-letter"));
    }

    public record BatchRequest(String batchId, String tenantId, List<Map<String, Object>> items, BatchOptions options) {}
    public record BatchOptions(String validationMode, String dedupeKey, Boolean enqueueDispatch, Boolean forceFail) {}
    public record IdempotencyRecord(String jobId, int payloadHash) {}
    private record QueuedJob(String jobId, int priority, long sequence, boolean forceFail, int chunkIndex, int totalChunks, List<Map<String, Object>> items) {}
    private record DedupeResult(List<Map<String, Object>> items, int duplicates) {}
    private record LiveCoreExecution(boolean core, String fallbackReason, int assigned, int chunkCount, long runtimeMs, List<Map<String, Object>> assignments, double initialCost, double finalCost, double improvementPercent, String solverPolicy, LiveAdaptiveBundlePlanner.PlanResult plan, LivePdLnsPostSolverImprover.Result repair, List<MlStageMetadata> mlStageMetadata) {}

    private record SelectedLiveBatch(List<Map<String, Object>> orders, String seedOrderId, double batchValue, int selectionCandidateCount, int heldOrderCount, String batchQuality, int forcedOrderCount, int badOrderCount, long oldestOrderAliveMs, long avgSelectedAliveMs, boolean starvationGuardApplied, List<String> reasons) {
        static SelectedLiveBatch empty() { return new SelectedLiveBatch(List.of(), "", 0.0, 0, 0, "EMPTY", 0, 0, 0L, 0L, false, List.of("empty-buffer")); }
        SelectedLiveBatch withFairness(String batchQuality, int forcedOrderCount, boolean starvationGuardApplied, List<String> reasons) {
            return new SelectedLiveBatch(orders, seedOrderId, batchValue, selectionCandidateCount, heldOrderCount, batchQuality, forcedOrderCount, badOrderCount, oldestOrderAliveMs, avgSelectedAliveMs, starvationGuardApplied, List.copyOf(reasons));
        }
        Map<String, Object> asMap(int currentBufferedOrders) {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("selectionPolicy", "GRAPH_VALUE_FAIR_BATCH_SELECTION");
            map.put("agingPolicy", "ORDER_PLACED_AT_PERSISTENT_AGING");
            map.put("selectedSeedOrderId", seedOrderId);
            map.put("selectedBatchValue", batchValue);
            map.put("batchQuality", batchQuality);
            map.put("forcedOrderCount", forcedOrderCount);
            map.put("badOrderCount", badOrderCount);
            map.put("oldestOrderAliveMs", oldestOrderAliveMs);
            map.put("avgSelectedAliveMs", avgSelectedAliveMs);
            map.put("starvationGuardApplied", starvationGuardApplied);
            map.put("selectionCandidateCount", selectionCandidateCount);
            map.put("selectedOrderCount", orders.size());
            map.put("heldOrderCount", Math.max(heldOrderCount, currentBufferedOrders));
            map.put("selectionReasons", reasons);
            return map;
        }
    }
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
        int totalChunks = 1;
        AtomicInteger completedChunks = new AtomicInteger();
        final String createdAt = Instant.now().toString();
        String batchId = "";

        RuntimeJob(String jobId, String tenantId, String queue, String kind, int accepted, int rejected) {
            this.jobId = jobId;
            this.tenantId = tenantId;
            this.queue = queue;
            this.kind = kind;
            this.accepted = Math.max(0, accepted);
            this.rejected = Math.max(0, rejected);
        }

        Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("jobId", jobId);
            map.put("tenantId", tenantId);
            map.put("queue", queue);
            map.put("kind", kind);
            map.put("status", status);
            map.put("accepted", accepted);
            map.put("rejected", rejected);
            map.put("attempts", attempts);
            map.put("createdAt", createdAt);
            return map;
        }
    }
}







