package com.routechain.v2.streaming;

import com.routechain.v2.SchemaVersioned;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

@Component
public final class DispatchStreamingMetrics {
    private final AtomicLong consumedCount = new AtomicLong();
    private final AtomicLong producedCount = new AtomicLong();
    private final AtomicLong deadLetterCount = new AtomicLong();
    private final AtomicLong rejectedBackpressureCount = new AtomicLong();
    private final AtomicLong totalProcessingLatencyMs = new AtomicLong();
    private final AtomicInteger inFlight = new AtomicInteger();

    public void markConsumed() { consumedCount.incrementAndGet(); }
    public void markProduced() { producedCount.incrementAndGet(); }
    public void markDeadLetter() { deadLetterCount.incrementAndGet(); }
    public void markRejectedBackpressure() { rejectedBackpressureCount.incrementAndGet(); }
    public void addLatency(long latencyMs) { totalProcessingLatencyMs.addAndGet(Math.max(0L, latencyMs)); }
    public int incrementInFlight() { return inFlight.incrementAndGet(); }
    public void decrementInFlight() { inFlight.updateAndGet(value -> Math.max(0, value - 1)); }

    public Snapshot snapshot() {
        long consumed = consumedCount.get();
        return new Snapshot(
                "dispatch-streaming-metrics/v1",
                consumed,
                producedCount.get(),
                deadLetterCount.get(),
                rejectedBackpressureCount.get(),
                inFlight.get(),
                consumed == 0 ? 0.0 : (double) totalProcessingLatencyMs.get() / consumed);
    }

    public record Snapshot(
            String schemaVersion,
            long consumedCount,
            long producedCount,
            long deadLetterCount,
            long rejectedBackpressureCount,
            int inFlight,
            double avgProcessingLatencyMs) implements SchemaVersioned {
    }
}
