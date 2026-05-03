package com.routechain.v2.streaming;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.routechain.config.RouteChainDispatchV2Properties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertTrue;

class FileLakeDispatchBigDataSinkTest {

    @TempDir
    Path tempDir;

    @Test
    void writesDispatchResultsAsJsonl() throws Exception {
        RouteChainDispatchV2Properties properties = RouteChainDispatchV2Properties.defaults();
        properties.getStreaming().setFileSinkBaseDir(tempDir.toString());
        FileLakeDispatchBigDataSink sink = new FileLakeDispatchBigDataSink(properties, new ObjectMapper().findAndRegisterModules());

        sink.writeDispatchResult(new DispatchStreamingResultEnvelope(
                "dispatch-streaming-result-envelope/v1",
                "event-1",
                "trace-1",
                "region-a",
                Instant.parse("2026-04-16T12:00:00Z"),
                null,
                Map.of()));

        assertTrue(Files.walk(tempDir)
                .filter(Files::isRegularFile)
                .anyMatch(path -> path.getFileName().toString().endsWith(".jsonl")));
    }
}
