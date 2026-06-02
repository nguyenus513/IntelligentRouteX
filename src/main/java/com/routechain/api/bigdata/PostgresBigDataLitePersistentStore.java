package com.routechain.api.bigdata;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Map;

@Component
@Primary
@ConditionalOnProperty(prefix = "routechain.bigdata-lite.postgres", name = "enabled", havingValue = "true")
public final class PostgresBigDataLitePersistentStore implements BigDataLitePersistentStore {
    private final BigDataLitePostgresProperties properties;
    private final ObjectMapper objectMapper;

    public PostgresBigDataLitePersistentStore(BigDataLitePostgresProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        initialize();
    }

    @Override
    public void upsertJob(String jobId, String tenantId, String batchId, String queue, String kind, String status, int accepted, int rejected, int attempts) {
        execute("""
                insert into bigdata_lite_jobs(job_id, tenant_id, batch_id, queue_name, kind, status, accepted, rejected, attempts, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
                on conflict (job_id) do update set tenant_id=excluded.tenant_id, batch_id=excluded.batch_id, queue_name=excluded.queue_name,
                kind=excluded.kind, status=excluded.status, accepted=excluded.accepted, rejected=excluded.rejected, attempts=excluded.attempts, updated_at=now()
                """, statement -> {
            statement.setString(1, jobId);
            statement.setString(2, tenantId);
            statement.setString(3, batchId);
            statement.setString(4, queue);
            statement.setString(5, kind);
            statement.setString(6, status);
            statement.setInt(7, accepted);
            statement.setInt(8, rejected);
            statement.setInt(9, attempts);
        });
    }

    @Override
    public void appendEvent(String eventId, String jobId, String type, String timestamp, Map<String, Object> data) {
        execute("insert into bigdata_lite_events(event_id, job_id, event_type, occurred_at_text, payload_json) values (?, ?, ?, ?, ?) on conflict (event_id) do nothing", statement -> {
            statement.setString(1, eventId);
            statement.setString(2, jobId);
            statement.setString(3, type);
            statement.setString(4, timestamp);
            statement.setString(5, json(data));
        });
    }

    @Override
    public void markDeadLetter(String jobId, String reason) {
        execute("insert into bigdata_lite_dead_letter(job_id, reason, created_at) values (?, ?, now()) on conflict (job_id) do update set reason=excluded.reason, created_at=now()", statement -> {
            statement.setString(1, jobId);
            statement.setString(2, reason);
        });
    }

    @Override
    public void upsertResult(String jobId, Map<String, Object> summary) {
        execute("insert into bigdata_lite_results(job_id, summary_json, updated_at) values (?, ?, now()) on conflict (job_id) do update set summary_json=excluded.summary_json, updated_at=now()", statement -> {
            statement.setString(1, jobId);
            statement.setString(2, json(summary));
        });
    }

    private void initialize() {
        execute("""
                create table if not exists bigdata_lite_jobs(
                  job_id text primary key, tenant_id text, batch_id text, queue_name text, kind text, status text,
                  accepted integer, rejected integer, attempts integer, updated_at timestamptz default now())
                """, ignored -> { });
        execute("create table if not exists bigdata_lite_events(event_id text primary key, job_id text, event_type text, occurred_at_text text, payload_json text)", ignored -> { });
        execute("create table if not exists bigdata_lite_dead_letter(job_id text primary key, reason text, created_at timestamptz default now())", ignored -> { });
        execute("create table if not exists bigdata_lite_results(job_id text primary key, summary_json text, updated_at timestamptz default now())", ignored -> { });
    }

    private void execute(String sql, SqlBinder binder) {
        try (Connection connection = DriverManager.getConnection(properties.getUrl(), properties.getUsername(), properties.getPassword());
             PreparedStatement statement = connection.prepareStatement(sql)) {
            binder.bind(statement);
            statement.executeUpdate();
        } catch (SQLException exception) {
            throw new IllegalStateException("bigdata-lite postgres write failed", exception);
        }
    }

    private String json(Map<String, Object> data) {
        try {
            return objectMapper.writeValueAsString(data == null ? Map.of() : data);
        } catch (JsonProcessingException exception) {
            return "{}";
        }
    }

    private interface SqlBinder {
        void bind(PreparedStatement statement) throws SQLException;
    }
}
