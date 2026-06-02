package com.routechain.api.bigdata;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "routechain.bigdata-lite.core")
public final class BigDataLiteCoreProperties {
    private boolean enabled = false;
    private int syntheticDriverCount = 500;
    private int maxOrdersPerChunk = 1000;
    private int promisedEtaMinutes = 45;
    private long timeoutMs = 5_000L;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public int getSyntheticDriverCount() { return syntheticDriverCount; }
    public void setSyntheticDriverCount(int syntheticDriverCount) { this.syntheticDriverCount = syntheticDriverCount; }
    public int getMaxOrdersPerChunk() { return maxOrdersPerChunk; }
    public void setMaxOrdersPerChunk(int maxOrdersPerChunk) { this.maxOrdersPerChunk = maxOrdersPerChunk; }
    public int getPromisedEtaMinutes() { return promisedEtaMinutes; }
    public void setPromisedEtaMinutes(int promisedEtaMinutes) { this.promisedEtaMinutes = promisedEtaMinutes; }
    public long getTimeoutMs() { return timeoutMs; }
    public void setTimeoutMs(long timeoutMs) { this.timeoutMs = timeoutMs; }
}
