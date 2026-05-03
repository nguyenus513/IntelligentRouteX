package com.routechain.v2.streaming;

import com.routechain.v2.selector.SelectorTrainingTrace;

import java.util.List;

public interface DispatchBigDataSink {
    void writeDispatchResult(DispatchStreamingResultEnvelope envelope);

    void writeTrainingTraces(String traceId, List<SelectorTrainingTrace> traces);

}
