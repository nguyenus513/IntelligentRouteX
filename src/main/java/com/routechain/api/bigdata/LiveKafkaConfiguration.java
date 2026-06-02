package com.routechain.api.bigdata;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

import java.util.HashMap;
import java.util.Map;

@Configuration
@ConditionalOnProperty(prefix = "routechain.live-kafka", name = "enabled", havingValue = "true")
public class LiveKafkaConfiguration {
    @Bean
    @ConditionalOnMissingBean(ProducerFactory.class)
    ProducerFactory<String, Object> liveProducerFactory(RouteChainDispatchV2Properties properties) {
        Map<String, Object> config = new HashMap<>();
        config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getStreaming().getBootstrapServers());
        config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        config.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
        return new DefaultKafkaProducerFactory<>(config);
    }

    @Bean
    @ConditionalOnMissingBean(KafkaTemplate.class)
    KafkaTemplate<String, Object> liveKafkaTemplate(ProducerFactory<String, Object> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }

    @Bean
    NewTopic liveOrderTopic(LiveKafkaProperties properties, RouteChainDispatchV2Properties dispatchProperties) {
        return new NewTopic(properties.getOrderTopic(), dispatchProperties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    NewTopic liveTelemetryTopic(LiveKafkaProperties properties, RouteChainDispatchV2Properties dispatchProperties) {
        return new NewTopic(properties.getTelemetryTopic(), dispatchProperties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    NewTopic liveResultTopic(LiveKafkaProperties properties, RouteChainDispatchV2Properties dispatchProperties) {
        return new NewTopic(properties.getResultTopic(), dispatchProperties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    ConsumerFactory<String, LiveKafkaEnvelope> liveKafkaConsumerFactory(RouteChainDispatchV2Properties properties,
                                                                       LiveKafkaProperties liveProperties) {
        Map<String, Object> config = new HashMap<>();
        config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getStreaming().getBootstrapServers());
        config.put(ConsumerConfig.GROUP_ID_CONFIG, liveProperties.getConsumerGroupId());
        config.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        config.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, JsonDeserializer.class);
        config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
        config.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        config.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 50);
        JsonDeserializer<LiveKafkaEnvelope> deserializer = new JsonDeserializer<>(LiveKafkaEnvelope.class);
        deserializer.addTrustedPackages("com.routechain", "java.util", "java.time");
        return new DefaultKafkaConsumerFactory<>(config, new StringDeserializer(), deserializer);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, LiveKafkaEnvelope> liveKafkaListenerContainerFactory(
            LiveKafkaProperties properties,
            ConsumerFactory<String, LiveKafkaEnvelope> liveKafkaConsumerFactory) {
        ConcurrentKafkaListenerContainerFactory<String, LiveKafkaEnvelope> factory = new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(liveKafkaConsumerFactory);
        factory.setConcurrency(Math.max(1, properties.getConcurrency()));
        return factory;
    }
}
