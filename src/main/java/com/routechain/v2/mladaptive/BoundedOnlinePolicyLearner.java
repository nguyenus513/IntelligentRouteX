package com.routechain.v2.mladaptive;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;

public final class BoundedOnlinePolicyLearner {
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private final Map<String, LinkedHashMap<String, ActionStats>> state = new LinkedHashMap<>();
    private final AtomicLong sequence = new AtomicLong();
    private Config config = Config.defaults();
    private long evictedContextCount;
    private long observedDecisionCount;

    public synchronized void configure(Config config) {
        this.config = config == null ? Config.defaults() : config.normalized();
        compact();
    }

    public synchronized BatchDecision suggestBatchSize(BatchContext context, int baseBatchSize, int maxBatchSize) {
        long started = System.nanoTime();
        Config active = config.normalized();
        int base = Math.max(1, baseBatchSize);
        int max = Math.max(1, maxBatchSize);
        if (!active.enabled()) {
            return BatchDecision.disabled(base, latencyMs(started));
        }
        String contextKey = contextKey(context);
        List<Integer> candidates = batchCandidates(base, max);
        LinkedHashMap<String, ActionStats> actions = state.computeIfAbsent(contextKey, ignored -> new LinkedHashMap<>());
        Map<String, ActionStats> eligibleActions = new LinkedHashMap<>();
        for (int candidate : candidates) {
            String actionKey = "batch:" + candidate;
            actions.putIfAbsent(actionKey, ActionStats.empty());
            eligibleActions.put(actionKey, actions.get(actionKey));
        }
        String selectedAction = selectAction(eligibleActions, active.explorationRate());
        int suggested = parseBatchAction(selectedAction, base);
        boolean applied = !active.shadowOnly() && suggested != base;
        long latencyMs = latencyMs(started);
        if (latencyMs > active.maxLearningLatencyMs()) {
            applied = false;
            suggested = base;
        }
        compact();
        return new BatchDecision(
                "learn-" + sequence.incrementAndGet(),
                active.enabled(),
                active.shadowOnly(),
                contextKey,
                selectedAction,
                base,
                suggested,
                applied,
                latencyMs,
                actions.getOrDefault(selectedAction, ActionStats.empty()).ewmaReward(),
                active.explorationRate(),
                latencyMs > active.maxLearningLatencyMs() ? "latency-budget-fallback" : "bounded-ewma-policy");
    }

    public synchronized OutcomeTelemetry observe(BatchDecision decision, Outcome outcome) {
        if (decision == null || outcome == null || !decision.enabled()) {
            return OutcomeTelemetry.empty(snapshot());
        }
        LinkedHashMap<String, ActionStats> actions = state.computeIfAbsent(decision.contextKey(), ignored -> new LinkedHashMap<>());
        ActionStats previous = actions.getOrDefault(decision.actionKey(), ActionStats.empty());
        double reward = reward(outcome);
        actions.put(decision.actionKey(), previous.update(reward, outcome.runtimeMs(), outcome.lateRate()));
        observedDecisionCount++;
        compact();
        return new OutcomeTelemetry(round(reward), snapshot());
    }

    public synchronized Snapshot snapshot() {
        return new Snapshot(
                "bounded-online-learning/v1",
                config.enabled(),
                config.shadowOnly(),
                state.size(),
                state.values().stream().mapToInt(Map::size).sum(),
                evictedContextCount,
                observedDecisionCount,
                estimateStateKb(),
                Instant.now().toString());
    }

    public synchronized void save(Path path) throws IOException {
        if (path == null || !config.enabled()) return;
        Files.createDirectories(path.getParent());
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("snapshot", snapshot());
        payload.put("state", state);
        byte[] bytes = OBJECT_MAPPER.writerWithDefaultPrettyPrinter().writeValueAsBytes(payload);
        if (bytes.length <= config.maxStateFileKb() * 1024L) {
            Files.write(path, bytes);
        }
    }

    public synchronized void load(Path path) throws IOException {
        if (path == null || !Files.exists(path)) return;
        Map<String, Object> payload = OBJECT_MAPPER.readValue(Files.readAllBytes(path), new TypeReference<>() {});
        Object rawState = payload.get("state");
        if (!(rawState instanceof Map<?, ?> rawMap)) return;
        state.clear();
        for (Map.Entry<?, ?> contextEntry : rawMap.entrySet()) {
            LinkedHashMap<String, ActionStats> actions = new LinkedHashMap<>();
            if (contextEntry.getValue() instanceof Map<?, ?> rawActions) {
                for (Map.Entry<?, ?> actionEntry : rawActions.entrySet()) {
                    ActionStats stats = OBJECT_MAPPER.convertValue(actionEntry.getValue(), ActionStats.class);
                    actions.put(String.valueOf(actionEntry.getKey()), stats == null ? ActionStats.empty() : stats);
                }
            }
            state.put(String.valueOf(contextEntry.getKey()), actions);
        }
        compact();
    }

    private void compact() {
        Config active = config.normalized();
        for (LinkedHashMap<String, ActionStats> actions : state.values()) {
            while (actions.size() > active.maxActionsPerContext()) {
                String evict = actions.entrySet().stream()
                        .min(Comparator.comparingLong((Map.Entry<String, ActionStats> entry) -> entry.getValue().count())
                                .thenComparingLong(entry -> entry.getValue().lastUpdatedMs()))
                        .map(Map.Entry::getKey)
                        .orElse(null);
                if (evict == null) break;
                actions.remove(evict);
            }
        }
        while (state.size() > active.maxContexts() || estimateStateKb() > active.maxStateFileKb()) {
            String evict = state.entrySet().stream()
                    .min(Comparator.comparingLong((Map.Entry<String, LinkedHashMap<String, ActionStats>> entry) -> contextUse(entry.getValue()))
                            .thenComparingLong(entry -> contextLastUpdated(entry.getValue())))
                    .map(Map.Entry::getKey)
                    .orElse(null);
            if (evict == null) break;
            state.remove(evict);
            evictedContextCount++;
        }
    }

    private String selectAction(Map<String, ActionStats> actions, double explorationRate) {
        if (actions.isEmpty()) return "batch:1";
        if (ThreadLocalRandom.current().nextDouble() < Math.max(0.0, Math.min(0.25, explorationRate))) {
            List<String> keys = new ArrayList<>(actions.keySet());
            return keys.get(ThreadLocalRandom.current().nextInt(keys.size()));
        }
        return actions.entrySet().stream()
                .max(Comparator.comparingDouble((Map.Entry<String, ActionStats> entry) -> entry.getValue().ewmaReward())
                        .thenComparingLong(entry -> -entry.getValue().ewmaRuntimeMs()))
                .map(Map.Entry::getKey)
                .orElse(actions.keySet().iterator().next());
    }

    private List<Integer> batchCandidates(int base, int max) {
        int down = Math.max(1, (int) Math.floor(base * 0.9));
        int up = Math.min(max, Math.max(base + 1, (int) Math.ceil(base * 1.1)));
        return List.of(down, base, up).stream().distinct().sorted().toList();
    }

    private String contextKey(BatchContext context) {
        BatchContext safe = context == null ? BatchContext.empty() : context;
        return String.join("|",
                safe.loadBucket(),
                safe.urgencyBucket(),
                safe.ageBucket(),
                safe.badOrderBucket(),
                safe.similarityBucket());
    }

    private double reward(Outcome outcome) {
        double reward = outcome.assignedRate() * 40.0
                + outcome.onTimeRate() * 40.0
                + outcome.improvementPercent() * 0.10
                - outcome.lateRate() * 50.0
                - (outcome.runtimeBreach() ? 30.0 : 0.0)
                - (outcome.safetyViolation() ? 100.0 : 0.0)
                - (outcome.fallbackUsed() ? 40.0 : 0.0);
        return Math.max(-200.0, Math.min(120.0, reward));
    }

    private int parseBatchAction(String action, int fallback) {
        if (action == null || !action.startsWith("batch:")) return fallback;
        try { return Math.max(1, Integer.parseInt(action.substring("batch:".length()))); } catch (NumberFormatException ignored) { return fallback; }
    }

    private long contextUse(Map<String, ActionStats> actions) {
        return actions.values().stream().mapToLong(ActionStats::count).sum();
    }

    private long contextLastUpdated(Map<String, ActionStats> actions) {
        return actions.values().stream().mapToLong(ActionStats::lastUpdatedMs).max().orElse(0L);
    }

    private long estimateStateKb() {
        long bytes = 128L;
        for (Map.Entry<String, LinkedHashMap<String, ActionStats>> context : state.entrySet()) {
            bytes += context.getKey().length() * 2L + 64L;
            bytes += context.getValue().size() * 96L;
        }
        return Math.max(1L, (bytes + 1023L) / 1024L);
    }

    private long latencyMs(long startedNanos) {
        return Math.max(0L, (System.nanoTime() - startedNanos) / 1_000_000L);
    }

    private static double round(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }

    public record Config(boolean enabled, boolean shadowOnly, int maxContexts, int maxActionsPerContext, int maxStateFileKb, long maxLearningLatencyMs, double explorationRate) {
        public static Config defaults() {
            return new Config(true, false, 256, 8, 512, 2L, 0.03);
        }

        Config normalized() {
            return new Config(enabled, shadowOnly, Math.max(8, maxContexts), Math.max(2, maxActionsPerContext), Math.max(32, maxStateFileKb), Math.max(1L, maxLearningLatencyMs), Math.max(0.0, Math.min(0.25, explorationRate)));
        }
    }

    public record BatchContext(String loadBucket, String urgencyBucket, String ageBucket, String badOrderBucket, String similarityBucket) {
        public static BatchContext empty() {
            return new BatchContext("load-low", "urgency-normal", "age-fresh", "bad-low", "sim-unknown");
        }
    }

    public record BatchDecision(String decisionId, boolean enabled, boolean shadowOnly, String contextKey, String actionKey, int baseBatchSize, int suggestedBatchSize, boolean appliedAsHint, long latencyMs, double expectedReward, double explorationRate, String reason) {
        public static BatchDecision disabled(int baseBatchSize, long latencyMs) {
            return new BatchDecision("learn-disabled", false, false, "disabled", "batch:" + baseBatchSize, baseBatchSize, baseBatchSize, false, latencyMs, 0.0, 0.0, "learning-disabled");
        }

        public Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("decisionId", decisionId);
            map.put("enabled", enabled);
            map.put("mode", shadowOnly ? "SHADOW" : "ASSIST");
            map.put("contextKey", contextKey);
            map.put("actionKey", actionKey);
            map.put("baseBatchSize", baseBatchSize);
            map.put("suggestedBatchSize", suggestedBatchSize);
            map.put("appliedAsHint", appliedAsHint);
            map.put("learningLatencyMs", latencyMs);
            map.put("expectedReward", expectedReward);
            map.put("explorationRate", explorationRate);
            map.put("reason", reason);
            return map;
        }
    }

    public record Outcome(double assignedRate, double onTimeRate, double lateRate, double improvementPercent, long runtimeMs, boolean runtimeBreach, boolean safetyViolation, boolean fallbackUsed) {
    }

    public record OutcomeTelemetry(double reward, Snapshot snapshot) {
        static OutcomeTelemetry empty(Snapshot snapshot) {
            return new OutcomeTelemetry(0.0, snapshot);
        }
    }

    public record Snapshot(String schemaVersion, boolean enabled, boolean shadowOnly, int contextCount, int actionCount, long evictedContextCount, long observedDecisionCount, long stateSizeKb, String updatedAt) {
        public Map<String, Object> asMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("schemaVersion", schemaVersion);
            map.put("enabled", enabled);
            map.put("mode", shadowOnly ? "SHADOW" : "ASSIST");
            map.put("contextCount", contextCount);
            map.put("actionCount", actionCount);
            map.put("evictedContextCount", evictedContextCount);
            map.put("observedDecisionCount", observedDecisionCount);
            map.put("stateSizeKb", stateSizeKb);
            map.put("updatedAt", updatedAt);
            return map;
        }
    }

    @JsonAutoDetect(fieldVisibility = JsonAutoDetect.Visibility.ANY)
    public static final class ActionStats {
        private long count;
        private double ewmaReward;
        private long ewmaRuntimeMs;
        private double ewmaLateRisk;
        private long lastUpdatedMs;

        public ActionStats() {
            this(0L, 0.0, 0L, 0.0, 0L);
        }

        @JsonCreator
        public ActionStats(@JsonProperty("count") long count,
                           @JsonProperty("ewmaReward") double ewmaReward,
                           @JsonProperty("ewmaRuntimeMs") long ewmaRuntimeMs,
                           @JsonProperty("ewmaLateRisk") double ewmaLateRisk,
                           @JsonProperty("lastUpdatedMs") long lastUpdatedMs) {
            this.count = Math.max(0L, count);
            this.ewmaReward = ewmaReward;
            this.ewmaRuntimeMs = Math.max(0L, ewmaRuntimeMs);
            this.ewmaLateRisk = Math.max(0.0, ewmaLateRisk);
            this.lastUpdatedMs = Math.max(0L, lastUpdatedMs);
        }

        static ActionStats empty() {
            return new ActionStats();
        }

        ActionStats update(double reward, long runtimeMs, double lateRisk) {
            double alpha = 0.05;
            if (count == 0L) {
                return new ActionStats(1L, round(reward), Math.max(0L, runtimeMs), Math.max(0.0, lateRisk), System.currentTimeMillis());
            }
            return new ActionStats(
                    count + 1L,
                    round((ewmaReward * (1.0 - alpha)) + (reward * alpha)),
                    Math.round((ewmaRuntimeMs * (1.0 - alpha)) + (Math.max(0L, runtimeMs) * alpha)),
                    round((ewmaLateRisk * (1.0 - alpha)) + (Math.max(0.0, lateRisk) * alpha)),
                    System.currentTimeMillis());
        }

        public long count() { return count; }
        public double ewmaReward() { return ewmaReward; }
        public long ewmaRuntimeMs() { return ewmaRuntimeMs; }
        public double ewmaLateRisk() { return ewmaLateRisk; }
        public long lastUpdatedMs() { return lastUpdatedMs; }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ActionStats that)) return false;
            return count == that.count && Double.compare(ewmaReward, that.ewmaReward) == 0 && ewmaRuntimeMs == that.ewmaRuntimeMs && Double.compare(ewmaLateRisk, that.ewmaLateRisk) == 0 && lastUpdatedMs == that.lastUpdatedMs;
        }

        @Override
        public int hashCode() {
            return Objects.hash(count, ewmaReward, ewmaRuntimeMs, ewmaLateRisk, lastUpdatedMs);
        }
    }
}
