package com.routechain.v2.streaming;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

import java.util.HashMap;
import java.util.Map;

@Configuration
@ConditionalOnProperty(prefix = "routechain.dispatch-v2.streaming", name = "enabled", havingValue = "true")
public class DispatchKafkaConfiguration {

    @Bean
    DispatchStreamingKeyResolver dispatchStreamingKeyResolver(RouteChainDispatchV2Properties properties) {
        return new DispatchStreamingKeyResolver(properties);
    }

    @Bean
    KafkaAdmin dispatchKafkaAdmin(RouteChainDispatchV2Properties properties) {
        return new KafkaAdmin(Map.of(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getStreaming().getBootstrapServers()));
    }

    @Bean
    NewTopic dispatchInputTopic(RouteChainDispatchV2Properties properties) {
        return new NewTopic(properties.getStreaming().getInputTopic(), properties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    NewTopic dispatchOutputTopic(RouteChainDispatchV2Properties properties) {
        return new NewTopic(properties.getStreaming().getOutputTopic(), properties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    NewTopic dispatchDeadLetterTopic(RouteChainDispatchV2Properties properties) {
        return new NewTopic(properties.getStreaming().getDeadLetterTopic(), properties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    ProducerFactory<String, Object> dispatchProducerFactory(RouteChainDispatchV2Properties properties) {
        Map<String, Object> config = new HashMap<>();
        config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getStreaming().getBootstrapServers());
        config.put(ProducerConfig.CLIENT_ID_CONFIG, properties.getStreaming().getClientId() + "-producer");
        config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);
        config.put(ProducerConfig.ACKS_CONFIG, "all");
        config.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        config.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
        return new DefaultKafkaProducerFactory<>(config);
    }

    @Bean
    KafkaTemplate<String, Object> dispatchKafkaTemplate(ProducerFactory<String, Object> dispatchProducerFactory) {
        return new KafkaTemplate<>(dispatchProducerFactory);
    }

    @Bean
    ConsumerFactory<String, DispatchStreamingEnvelope> dispatchConsumerFactory(RouteChainDispatchV2Properties properties) {
        Map<String, Object> config = new HashMap<>();
        config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getStreaming().getBootstrapServers());
        config.put(ConsumerConfig.GROUP_ID_CONFIG, properties.getStreaming().getConsumerGroupId());
        config.put(ConsumerConfig.CLIENT_ID_CONFIG, properties.getStreaming().getClientId() + "-consumer");
        config.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        config.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, JsonDeserializer.class);
        config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
        config.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        JsonDeserializer<DispatchStreamingEnvelope> deserializer = new JsonDeserializer<>(DispatchStreamingEnvelope.class);
        deserializer.addTrustedPackages("com.routechain", "java.util", "java.time");
        return new DefaultKafkaConsumerFactory<>(config, new StringDeserializer(), deserializer);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, DispatchStreamingEnvelope> dispatchKafkaListenerContainerFactory(
            RouteChainDispatchV2Properties properties,
            ConsumerFactory<String, DispatchStreamingEnvelope> dispatchConsumerFactory) {
        ConcurrentKafkaListenerContainerFactory<String, DispatchStreamingEnvelope> factory = new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(dispatchConsumerFactory);
        factory.setConcurrency(Math.max(1, properties.getStreaming().getConcurrency()));
        return factory;
    }
}
