package com.routechain.api.bigdata;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "routechain.bigdata-lite.kafka")
public final class BigDataLiteKafkaProperties {
    private boolean enabled = false;
    private boolean fallbackToLocal = true;
    private String inputTopic = "irx.bigdata.chunks.v1";
    private String resultTopic = "irx.bigdata.results.v1";
    private String consumerGroupId = "irx-bigdata-lite";
    private int concurrency = 2;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public boolean isFallbackToLocal() { return fallbackToLocal; }
    public void setFallbackToLocal(boolean fallbackToLocal) { this.fallbackToLocal = fallbackToLocal; }
    public String getInputTopic() { return inputTopic; }
    public void setInputTopic(String inputTopic) { this.inputTopic = inputTopic; }
    public String getResultTopic() { return resultTopic; }
    public void setResultTopic(String resultTopic) { this.resultTopic = resultTopic; }
    public String getConsumerGroupId() { return consumerGroupId; }
    public void setConsumerGroupId(String consumerGroupId) { this.consumerGroupId = consumerGroupId; }
    public int getConcurrency() { return concurrency; }
    public void setConcurrency(int concurrency) { this.concurrency = concurrency; }
}
