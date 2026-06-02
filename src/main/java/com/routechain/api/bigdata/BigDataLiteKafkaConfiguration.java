package com.routechain.api.bigdata;

import com.routechain.config.RouteChainDispatchV2Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

import java.util.HashMap;
import java.util.Map;

@Configuration
@ConditionalOnProperty(prefix = "routechain.bigdata-lite.kafka", name = "enabled", havingValue = "true")
public class BigDataLiteKafkaConfiguration {
    @Bean
    @ConditionalOnMissingBean(ProducerFactory.class)
    ProducerFactory<String, Object> bigDataLiteProducerFactory(RouteChainDispatchV2Properties properties) {
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
    KafkaTemplate<String, Object> bigDataLiteKafkaTemplate(ProducerFactory<String, Object> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }

    @Bean
    NewTopic bigDataLiteInputTopic(BigDataLiteKafkaProperties properties,
                                   RouteChainDispatchV2Properties dispatchProperties) {
        return new NewTopic(properties.getInputTopic(), dispatchProperties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    NewTopic bigDataLiteResultTopic(BigDataLiteKafkaProperties properties,
                                    RouteChainDispatchV2Properties dispatchProperties) {
        return new NewTopic(properties.getResultTopic(), dispatchProperties.getStreaming().getPartitions(), (short) 1);
    }

    @Bean
    ConsumerFactory<String, BigDataLiteKafkaEnvelope> bigDataLiteConsumerFactory(RouteChainDispatchV2Properties properties,
                                                                                BigDataLiteKafkaProperties kafkaProperties) {
        Map<String, Object> config = new HashMap<>();
        config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, properties.getStreaming().getBootstrapServers());
        config.put(ConsumerConfig.GROUP_ID_CONFIG, kafkaProperties.getConsumerGroupId());
        config.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
        config.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, JsonDeserializer.class);
        config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
        config.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        config.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 1);
        config.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 1_800_000);
        JsonDeserializer<BigDataLiteKafkaEnvelope> deserializer = new JsonDeserializer<>(BigDataLiteKafkaEnvelope.class);
        deserializer.addTrustedPackages("com.routechain", "java.util", "java.time");
        return new DefaultKafkaConsumerFactory<>(config, new StringDeserializer(), deserializer);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, BigDataLiteKafkaEnvelope> bigDataLiteKafkaListenerContainerFactory(
            BigDataLiteKafkaProperties properties,
            ConsumerFactory<String, BigDataLiteKafkaEnvelope> bigDataLiteConsumerFactory) {
        ConcurrentKafkaListenerContainerFactory<String, BigDataLiteKafkaEnvelope> factory = new ConcurrentKafkaListenerContainerFactory<>();
        factory.setConsumerFactory(bigDataLiteConsumerFactory);
        factory.setConcurrency(Math.max(1, properties.getConcurrency()));
        return factory;
    }
}
