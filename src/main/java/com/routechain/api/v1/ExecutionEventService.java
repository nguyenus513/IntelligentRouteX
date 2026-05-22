package com.routechain.api.v1;

import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

@Service
public final class ExecutionEventService {
    private final Map<String, List<Map<String, Object>>> eventsByExecution = new ConcurrentHashMap<>();
    private final Map<String, CopyOnWriteArrayList<SseEmitter>> subscribers = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1);

    public Map<String, Object> emit(String executionId, String stage, String status, int percent, String message, Object data) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("executionId", executionId);
        event.put("sequence", sequence.getAndIncrement());
        event.put("stage", stage);
        event.put("status", status);
        event.put("percent", percent);
        event.put("message", message);
        event.put("timestamp", Instant.now().toString());
        event.put("data", data == null ? Map.of() : data);
        eventsByExecution.computeIfAbsent(executionId, ignored -> new CopyOnWriteArrayList<>()).add(event);
        for (SseEmitter emitter : subscribers.getOrDefault(executionId, new CopyOnWriteArrayList<>())) {
            try {
                emitter.send(SseEmitter.event().name(stage).id(String.valueOf(event.get("sequence"))).data(event));
            } catch (IOException error) {
                emitter.completeWithError(error);
                subscribers.getOrDefault(executionId, new CopyOnWriteArrayList<>()).remove(emitter);
            }
        }
        return event;
    }

    public Map<String, Object> timeline(String executionId) {
        List<Map<String, Object>> events = eventsByExecution.getOrDefault(executionId, List.of());
        Map<String, Map<String, Object>> latestByStage = new LinkedHashMap<>();
        for (Map<String, Object> event : events) latestByStage.put(String.valueOf(event.get("stage")), event);
        List<Map<String, Object>> stages = new ArrayList<>();
        for (Map<String, Object> event : latestByStage.values()) {
            stages.add(Map.of(
                    "stage", event.get("stage"),
                    "status", event.get("status"),
                    "percent", event.get("percent"),
                    "message", event.get("message"),
                    "timestamp", event.get("timestamp")));
        }
        String status = events.stream().anyMatch(event -> "FAILED".equals(event.get("status")))
                ? "FAILED"
                : events.stream().anyMatch(event -> "EXECUTION_COMPLETED".equals(event.get("stage"))) ? "COMPLETED" : "RUNNING";
        Object currentStage = events.isEmpty() ? "WAITING" : events.get(events.size() - 1).get("stage");
        return Map.of("executionId", executionId, "status", status, "currentStage", currentStage, "stages", stages);
    }

    public List<Map<String, Object>> history(String executionId) {
        return List.copyOf(eventsByExecution.getOrDefault(executionId, List.of()));
    }

    public SseEmitter subscribe(String executionId) {
        SseEmitter emitter = new SseEmitter(120_000L);
        subscribers.computeIfAbsent(executionId, ignored -> new CopyOnWriteArrayList<>()).add(emitter);
        emitter.onCompletion(() -> subscribers.getOrDefault(executionId, new CopyOnWriteArrayList<>()).remove(emitter));
        emitter.onTimeout(() -> subscribers.getOrDefault(executionId, new CopyOnWriteArrayList<>()).remove(emitter));
        for (Map<String, Object> event : history(executionId)) {
            try {
                emitter.send(SseEmitter.event().name(String.valueOf(event.get("stage"))).id(String.valueOf(event.get("sequence"))).data(event));
            } catch (IOException error) {
                emitter.completeWithError(error);
                break;
            }
        }
        return emitter;
    }
}
