package com.routechain.v2.harvest;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.routechain.config.RouteChainDispatchV2Properties;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public final class HarvestRailWriter implements AutoCloseable {
    private final boolean enabled;
    private final Path baseDirectory;
    private final long maxFileSizeBytes;
    private final ArrayBlockingQueue<QueuedRow> queue;
    private final ScheduledExecutorService flusher;
    private final ObjectMapper objectMapper;
    private final AtomicLong droppedCount = new AtomicLong();
    private final AtomicLong failureCount = new AtomicLong();

    public HarvestRailWriter(RouteChainDispatchV2Properties properties) {
        this.enabled = properties.getHarvest().isEnabled();
        this.baseDirectory = Path.of(properties.getHarvest().getBaseDir());
        this.maxFileSizeBytes = Math.max(1L, properties.getHarvest().getMaxFileSizeBytes());
        this.queue = new ArrayBlockingQueue<>(Math.max(64, properties.getHarvest().getQueueCapacity()));
        this.flusher = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "dispatch-v2-harvest-writer");
            thread.setDaemon(true);
            return thread;
        });
        this.objectMapper = JsonMapper.builder().findAndAddModules().build();
        if (enabled) {
            Duration flushInterval = properties.getHarvest().getFlushInterval();
            long flushEveryMs = Math.max(50L, flushInterval == null ? 250L : flushInterval.toMillis());
            flusher.scheduleWithFixedDelay(this::drainQuietly, flushEveryMs, flushEveryMs, TimeUnit.MILLISECONDS);
        }
    }

    public boolean write(HarvestFamily family, String runId, Map<String, Object> row) {
        if (!enabled || family == null || runId == null || runId.isBlank() || row == null) {
            return false;
        }
        boolean accepted = queue.offer(new QueuedRow(family, sanitize(runId), row));
        if (!accepted) {
            droppedCount.incrementAndGet();
        }
        return accepted;
    }

    public Map<String, Object> stats() {
        return Map.of(
                "harvestDropCount", droppedCount.get(),
                "harvestFailureCount", failureCount.get(),
                "queueDepth", queue.size());
    }

    public void flushNow() {
        drainQuietly();
    }

    @Override
    public void close() {
        flusher.shutdownNow();
        drainQuietly();
    }

    private void drainQuietly() {
        if (!enabled) {
            return;
        }
        QueuedRow row;
        while ((row = queue.poll()) != null) {
            try {
                append(row);
            } catch (IOException exception) {
                failureCount.incrementAndGet();
            }
        }
    }

    private void append(QueuedRow row) throws IOException {
        Path familyDir = baseDirectory.resolve(row.family().directoryName());
        Files.createDirectories(familyDir);
        byte[] payload = (objectMapper.writeValueAsString(row.row()) + System.lineSeparator()).getBytes(StandardCharsets.UTF_8);
        Path target = resolveTarget(familyDir, row.runId());
        Files.write(target, payload, StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.APPEND);
    }

    private Path resolveTarget(Path familyDir, String runId) throws IOException {
        Path candidate = familyDir.resolve(runId + ".jsonl");
        int part = 1;
        while (Files.exists(candidate) && Files.size(candidate) >= maxFileSizeBytes) {
            candidate = familyDir.resolve(runId + "-part" + part++ + ".jsonl");
        }
        return candidate;
    }

    private String sanitize(String raw) {
        return raw.replaceAll("[^a-zA-Z0-9._-]", "_");
    }

    private record QueuedRow(HarvestFamily family, String runId, Map<String, Object> row) {
    }
}
