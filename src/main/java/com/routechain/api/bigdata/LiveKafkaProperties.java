package com.routechain.api.bigdata;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "routechain.live-kafka")
public final class LiveKafkaProperties {
    private boolean enabled = false;
    private String orderTopic = "irx.live.orders.v1";
    private String telemetryTopic = "irx.live.telemetry.v1";
    private String resultTopic = "irx.live.results.v1";
    private String consumerGroupId = "irx-live-dispatch";
    private int concurrency = 2;
    private int maxBufferedOrders = 10_000;
    private int maxOrdersPerCycle = 100;
    private long maxWaitMs = 3_000L;
    private long flushIntervalMs = 1_000L;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getOrderTopic() { return orderTopic; }
    public void setOrderTopic(String orderTopic) { this.orderTopic = orderTopic; }
    public String getTelemetryTopic() { return telemetryTopic; }
    public void setTelemetryTopic(String telemetryTopic) { this.telemetryTopic = telemetryTopic; }
    public String getResultTopic() { return resultTopic; }
    public void setResultTopic(String resultTopic) { this.resultTopic = resultTopic; }
    public String getConsumerGroupId() { return consumerGroupId; }
    public void setConsumerGroupId(String consumerGroupId) { this.consumerGroupId = consumerGroupId; }
    public int getConcurrency() { return concurrency; }
    public void setConcurrency(int concurrency) { this.concurrency = concurrency; }
    public int getMaxBufferedOrders() { return maxBufferedOrders; }
    public void setMaxBufferedOrders(int maxBufferedOrders) { this.maxBufferedOrders = maxBufferedOrders; }
    public int getMaxOrdersPerCycle() { return maxOrdersPerCycle; }
    public void setMaxOrdersPerCycle(int maxOrdersPerCycle) { this.maxOrdersPerCycle = maxOrdersPerCycle; }
    public long getMaxWaitMs() { return maxWaitMs; }
    public void setMaxWaitMs(long maxWaitMs) { this.maxWaitMs = maxWaitMs; }
    public long getFlushIntervalMs() { return flushIntervalMs; }
    public void setFlushIntervalMs(long flushIntervalMs) { this.flushIntervalMs = flushIntervalMs; }
}
