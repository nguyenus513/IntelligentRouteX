package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public final class DispatchStreamingInfoContributor implements InfoContributor {
    private final RouteChainDispatchV2Properties properties;
    private final DispatchStreamingMetrics metrics;

    public DispatchStreamingInfoContributor(RouteChainDispatchV2Properties properties,
                                            DispatchStreamingMetrics metrics) {
        this.properties = properties;
        this.metrics = metrics;
    }

    @Override
    public void contribute(Info.Builder builder) {
        DispatchStreamingMetrics.Snapshot snapshot = metrics.snapshot();
        builder.withDetail("dispatchStreaming", Map.of(
                "enabled", properties.getStreaming().isEnabled(),
                "inputTopic", properties.getStreaming().getInputTopic(),
                "outputTopic", properties.getStreaming().getOutputTopic(),
                "deadLetterTopic", properties.getStreaming().getDeadLetterTopic(),
                "consumerGroupId", properties.getStreaming().getConsumerGroupId(),
                "concurrency", properties.getStreaming().getConcurrency(),
                "partitions", properties.getStreaming().getPartitions(),
                "maxInFlight", properties.getStreaming().getMaxInFlight(),
                "metrics", snapshot));
    }
}
