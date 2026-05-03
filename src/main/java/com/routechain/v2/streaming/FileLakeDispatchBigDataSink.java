package com.routechain.v2.streaming;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.routechain.config.RouteChainDispatchV2Properties;
import com.routechain.v2.selector.SelectorTrainingTrace;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDate;
import java.util.List;

@Component
@ConditionalOnProperty(prefix = "routechain.dispatch-v2.streaming", name = "file-sink-enabled", havingValue = "true")
public final class FileLakeDispatchBigDataSink implements DispatchBigDataSink {
    private final RouteChainDispatchV2Properties properties;
    private final ObjectMapper objectMapper;

    public FileLakeDispatchBigDataSink(RouteChainDispatchV2Properties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public void writeDispatchResult(DispatchStreamingResultEnvelope envelope) {
        append("dispatch-results", envelope);
    }

    @Override
    public void writeTrainingTraces(String traceId, List<SelectorTrainingTrace> traces) {
        if (traces == null || traces.isEmpty()) {
            return;
        }
        for (SelectorTrainingTrace trace : traces) {
            append("selector-training-traces", trace);
        }
    }

    private void append(String dataset, Object payload) {
        try {
            Path path = datasetPath(dataset);
            Files.createDirectories(path.getParent());
            Files.writeString(
                    path,
                    objectMapper.writeValueAsString(payload) + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        } catch (IOException exception) {
            throw new IllegalStateException("failed to write dispatch big-data sink", exception);
        }
    }

    private Path datasetPath(String dataset) {
        return Path.of(properties.getStreaming().getFileSinkBaseDir())
                .resolve(dataset)
                .resolve("dt=" + LocalDate.now())
                .resolve("part-00000.jsonl");
    }
}
