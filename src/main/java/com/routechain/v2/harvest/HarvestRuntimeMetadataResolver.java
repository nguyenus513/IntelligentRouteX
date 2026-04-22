package com.routechain.v2.harvest;

import com.routechain.config.RouteChainDispatchV2Properties;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public final class HarvestRuntimeMetadataResolver {
    private static final String UNKNOWN = "unknown";

    private final RouteChainDispatchV2Properties properties;

    public HarvestRuntimeMetadataResolver(RouteChainDispatchV2Properties properties) {
        this.properties = properties;
    }

    public HarvestRuntimeMetadata resolve() {
        LinkedHashMap<String, Object> sourceConfig = new LinkedHashMap<>();
        sourceConfig.put("weatherEnabled", properties.getWeather().isEnabled());
        sourceConfig.put("trafficEnabled", properties.getTraffic().isEnabled());
        sourceConfig.put("weatherBaseUrl", properties.getWeather().getBaseUrl());
        sourceConfig.put("trafficBaseUrl", properties.getTraffic().getBaseUrl());
        sourceConfig.put("forecastEnabled", properties.getMl().getForecast().isEnabled());
        sourceConfig.put("routeFinderEnabled", properties.getMl().getRoutefinder().isEnabled());
        sourceConfig.put("greedRlEnabled", properties.getMl().getGreedrl().isEnabled());
        sourceConfig.put("tabularEnabled", properties.getMl().getTabular().isEnabled());
        return new HarvestRuntimeMetadata(
                resolveCommitSha(),
                resolveMachineClass(),
                Instant.now(),
                Map.copyOf(sourceConfig));
    }

    private String resolveMachineClass() {
        return System.getProperty("os.name", UNKNOWN)
                + "|cpu=" + Runtime.getRuntime().availableProcessors();
    }

    private String resolveCommitSha() {
        Path gitDir = Path.of(".git");
        try {
            if (!Files.exists(gitDir)) {
                return UNKNOWN;
            }
            String head = Files.readString(gitDir.resolve("HEAD")).trim();
            if (!head.startsWith("ref: ")) {
                return sanitizeSha(head);
            }
            Path refPath = gitDir.resolve(head.substring(5).trim());
            if (Files.exists(refPath)) {
                return sanitizeSha(Files.readString(refPath).trim());
            }
        } catch (IOException ignored) {
            return UNKNOWN;
        }
        return UNKNOWN;
    }

    private String sanitizeSha(String sha) {
        if (sha == null || sha.isBlank()) {
            return UNKNOWN;
        }
        return sha.length() > 40 ? sha.substring(0, 40) : sha;
    }
}
