package com.routechain.api.bigdata;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.Region;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
public final class BigDataDispatchInputMapper {
    private final BigDataLiteCoreProperties properties;

    public BigDataDispatchInputMapper(BigDataLiteCoreProperties properties) {
        this.properties = properties;
    }

    public DispatchV2Request toRequest(String jobId, int chunkIndex, List<Map<String, Object>> items) {
        Instant now = Instant.now();
        List<Order> orders = new ArrayList<>();
        String regionId = "bigdata-region";
        for (int i = 0; i < items.size(); i++) {
            Map<String, Object> item = items.get(i);
            regionId = string(item, "regionId", regionId);
            String orderId = shortSafeId(string(item, "externalOrderId", string(item, "orderId", "ORD-" + (chunkIndex + 1) + "-" + (i + 1))));
            GeoPoint pickup = new GeoPoint(number(item, "pickupLat", number(item, "lat", 10.75)), number(item, "pickupLng", number(item, "lng", 106.67)));
            GeoPoint dropoff = new GeoPoint(number(item, "dropoffLat", pickup.latitude() + 0.01), number(item, "dropoffLng", pickup.longitude() + 0.01));
            Instant placedAt = instantFromEpochMs(epochMs(item, now.toEpochMilli(), "placedAtMs", "orderCreatedAtMs", "createdAtMs", "placedAt", "createdAt"), now);
            orders.add(new Order(orderId, pickup, dropoff, placedAt, now, intNumber(item, "promisedEtaMinutes", properties.getPromisedEtaMinutes()), booleanValue(item, "urgent", false)));
        }
        List<Driver> drivers = syntheticDrivers(regionId, Math.max(1, Math.min(properties.getSyntheticDriverCount(), Math.max(1, orders.size() / 5))));
        return new DispatchV2Request("dispatch-v2-request/v1", safeId(jobId) + "-chunk-" + chunkIndex, orders, drivers, List.of(new Region(regionId, regionId)), WeatherProfile.CLEAR, now);
    }

    private List<Driver> syntheticDrivers(String regionId, int count) {
        List<Driver> drivers = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            double offset = (i % 25) * 0.002;
            drivers.add(new Driver("DRV-" + regionId + "-" + (i + 1), new GeoPoint(10.75 + offset, 106.67 + offset)));
        }
        return drivers;
    }

    private String string(Map<String, Object> item, String key, String fallback) {
        Object value = item.get(key);
        return value == null || String.valueOf(value).isBlank() ? fallback : String.valueOf(value);
    }

    private double number(Map<String, Object> item, String key, double fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.doubleValue();
        try { return value == null ? fallback : Double.parseDouble(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private int intNumber(Map<String, Object> item, String key, int fallback) {
        Object value = item.get(key);
        if (value instanceof Number number) return number.intValue();
        try { return value == null ? fallback : Integer.parseInt(String.valueOf(value)); } catch (NumberFormatException ignored) { return fallback; }
    }

    private boolean booleanValue(Map<String, Object> item, String key, boolean fallback) {
        Object value = item.get(key);
        return value == null ? fallback : Boolean.parseBoolean(String.valueOf(value));
    }

    private long epochMs(Map<String, Object> item, long fallback, String... keys) {
        for (String key : keys) {
            Object value = item.get(key);
            Long parsed = parseEpochMs(value);
            if (parsed != null) return parsed;
        }
        return fallback;
    }

    private Long parseEpochMs(Object value) {
        if (value instanceof Number number) {
            long raw = number.longValue();
            return raw < 1_000_000_000_000L ? raw * 1000L : raw;
        }
        if (value == null || String.valueOf(value).isBlank()) return null;
        String text = String.valueOf(value).trim();
        try {
            long raw = Long.parseLong(text);
            return raw < 1_000_000_000_000L ? raw * 1000L : raw;
        } catch (NumberFormatException ignored) {
            try { return Instant.parse(text).toEpochMilli(); } catch (RuntimeException ignoredIso) { return null; }
        }
    }

    private Instant instantFromEpochMs(long epochMs, Instant fallback) {
        try { return Instant.ofEpochMilli(epochMs); } catch (RuntimeException ignored) { return fallback; }
    }

    private String safeId(String value) {
        String cleaned = value == null ? "live" : value.replaceAll("[^A-Za-z0-9_.-]", "-");
        return cleaned.isBlank() ? "live" : cleaned;
    }

    private String shortSafeId(String value) {
        String cleaned = safeId(value);
        return cleaned.length() <= 32 ? cleaned : cleaned.substring(0, 32);
    }
}
