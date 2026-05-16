package com.routechain.v2.live;

import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public final class DriverTelemetryStore {
    private final Map<String, DriverTelemetrySnapshot> drivers = new LinkedHashMap<>();

    public synchronized List<DriverTelemetrySnapshot> update(List<DriverTelemetrySnapshot> snapshots, Instant now) {
        for (DriverTelemetrySnapshot snapshot : snapshots == null ? List.<DriverTelemetrySnapshot>of() : snapshots) {
            if (snapshot == null || snapshot.driverId() == null || snapshot.driverId().isBlank()) {
                continue;
            }
            drivers.put(snapshot.driverId(), new DriverTelemetrySnapshot(
                    snapshot.driverId(),
                    snapshot.lat(),
                    snapshot.lng(),
                    snapshot.timestamp() == null ? now : snapshot.timestamp(),
                    snapshot.heading(),
                    snapshot.speed(),
                    snapshot.activeRouteId(),
                    snapshot.status() == null || snapshot.status().isBlank() ? "AVAILABLE" : snapshot.status()));
        }
        return all();
    }

    public synchronized List<DriverTelemetrySnapshot> all() {
        return List.copyOf(drivers.values());
    }

    public synchronized void clear() {
        drivers.clear();
    }
}
