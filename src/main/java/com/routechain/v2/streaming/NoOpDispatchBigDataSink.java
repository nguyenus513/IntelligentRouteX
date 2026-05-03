package com.routechain.v2.streaming;

import com.routechain.v2.selector.SelectorTrainingTrace;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
@ConditionalOnMissingBean(DispatchBigDataSink.class)
public final class NoOpDispatchBigDataSink implements DispatchBigDataSink {
    @Override
    public void writeDispatchResult(DispatchStreamingResultEnvelope envelope) {
    }

    @Override
    public void writeTrainingTraces(String traceId, List<SelectorTrainingTrace> traces) {
    }
}
