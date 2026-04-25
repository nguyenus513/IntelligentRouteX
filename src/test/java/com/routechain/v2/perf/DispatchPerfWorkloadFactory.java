package com.routechain.v2.perf;

import com.routechain.domain.Driver;
import com.routechain.domain.GeoPoint;
import com.routechain.domain.Order;
import com.routechain.domain.WeatherProfile;
import com.routechain.v2.DispatchV2Request;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public final class DispatchPerfWorkloadFactory {
    private static final double BASE_LAT = 10.7750;
    private static final double BASE_LON = 106.7000;
    private static final Instant BASE_DECISION_TIME = Instant.parse("2026-04-16T12:00:00Z");
    private static final List<GeoPoint> HCM_HOTSPOTS = List.of(
            new GeoPoint(10.7769, 106.7009),
            new GeoPoint(10.7294, 106.7219),
            new GeoPoint(10.8016, 106.7147),
            new GeoPoint(10.8411, 106.8098),
            new GeoPoint(10.7626, 106.6601));

    private DispatchPerfWorkloadFactory() {
    }

    public static DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize, String traceId) {
        return request(workloadSize, traceId, ScenarioWorldProfile.NORMAL_CLEAR);
    }

    public static DispatchV2Request request(DispatchPerfBenchmarkHarness.WorkloadSize workloadSize,
                                            String traceId,
                                            ScenarioWorldProfile profile) {
        Random random = new Random(workloadSize.seed());
        ScenarioWorldProfile effectiveProfile = profile == null ? ScenarioWorldProfile.NORMAL_CLEAR : profile;
        List<Order> orders = effectiveProfile == ScenarioWorldProfile.DENSE_BUNDLE_DEMO
                ? denseBundleDemoOrders(workloadSize.orderCount(), effectiveProfile)
                : orders(workloadSize.orderCount(), random, effectiveProfile);
        List<Driver> drivers = effectiveProfile == ScenarioWorldProfile.DENSE_BUNDLE_DEMO
                ? denseBundleDemoDrivers(workloadSize.driverCount())
                : drivers(workloadSize.driverCount(), random, effectiveProfile);
        return new DispatchV2Request(
                "dispatch-v2-request/v1",
                traceId,
                orders,
                drivers,
                List.of(),
                effectiveProfile.weatherProfile(),
                effectiveProfile.decisionTime());
    }

    private static List<Order> orders(int orderCount, Random random, ScenarioWorldProfile profile) {
        List<Order> orders = new ArrayList<>(orderCount);
        for (int index = 0; index < orderCount; index++) {
            GeoPoint hotspot = hotspot(index, random, profile);
            double pickupLat = jitter(hotspot.latitude(), random, profile.pickupAmplitude());
            double pickupLon = jitter(hotspot.longitude(), random, profile.pickupAmplitude());
            double dropLat = jitter(hotspot.latitude() + profile.dropOffset(), random, profile.dropAmplitude());
            double dropLon = jitter(hotspot.longitude() + profile.dropOffset(), random, profile.dropAmplitude());
            Instant readyAt = profile.decisionTime().plusSeconds((index % profile.readyBucketSpan()) * profile.readyStepSeconds());
            orders.add(new Order(
                    "order-" + index,
                    new GeoPoint(pickupLat, pickupLon),
                    new GeoPoint(dropLat, dropLon),
                    readyAt.minusSeconds(300),
                    readyAt,
                    profile.baseReadyWindowMinutes() + (index % profile.readyWindowSpread()),
                    index % profile.priorityInterval() == 0));
        }
        return List.copyOf(orders);
    }


    private static List<Order> denseBundleDemoOrders(int orderCount, ScenarioWorldProfile profile) {
        List<Order> orders = new ArrayList<>(orderCount);
        for (int index = 0; index < orderCount; index++) {
            int cluster = index / 4;
            int offset = index % 4;
            GeoPoint hotspot = HCM_HOTSPOTS.get(cluster % HCM_HOTSPOTS.size());
            double corridorLat = (offset - 1.5) * 0.00105;
            double sideStreetLon = (offset % 2 == 0 ? -0.00075 : 0.00075);
            double pickupLat = hotspot.latitude() + corridorLat;
            double pickupLon = hotspot.longitude() + sideStreetLon;
            double dropLat = hotspot.latitude() + profile.dropOffset() + (offset - 1.5) * 0.00125;
            double dropLon = hotspot.longitude() + profile.dropOffset() + (offset % 2 == 0 ? -0.00100 : 0.00100);
            Instant readyAt = profile.decisionTime().plusSeconds((offset % profile.readyBucketSpan()) * profile.readyStepSeconds());
            orders.add(new Order(
                    "order-" + index,
                    new GeoPoint(pickupLat, pickupLon),
                    new GeoPoint(dropLat, dropLon),
                    readyAt.minusSeconds(300),
                    readyAt,
                    profile.baseReadyWindowMinutes() + (offset % profile.readyWindowSpread()),
                    index % profile.priorityInterval() == 0));
        }
        return List.copyOf(orders);
    }

    private static List<Driver> denseBundleDemoDrivers(int driverCount) {
        List<Driver> drivers = new ArrayList<>(driverCount);
        for (int index = 0; index < driverCount; index++) {
            GeoPoint hotspot = HCM_HOTSPOTS.get(index % HCM_HOTSPOTS.size());
            drivers.add(new Driver(
                    "driver-" + index,
                    new GeoPoint(hotspot.latitude() - 0.0012, hotspot.longitude() - 0.0012)));
        }
        return List.copyOf(drivers);
    }
    private static List<Driver> drivers(int driverCount, Random random, ScenarioWorldProfile profile) {
        List<Driver> drivers = new ArrayList<>(driverCount);
        for (int index = 0; index < driverCount; index++) {
            GeoPoint hotspot = hotspot(index + 1, random, profile);
            drivers.add(new Driver(
                            "driver-" + index,
                    new GeoPoint(
                            jitter(hotspot.latitude() - profile.driverOffset(), random, profile.driverAmplitude()),
                            jitter(hotspot.longitude() - profile.driverOffset(), random, profile.driverAmplitude()))));
        }
        return List.copyOf(drivers);
    }

    private static GeoPoint hotspot(int index, Random random, ScenarioWorldProfile profile) {
        if (profile == ScenarioWorldProfile.DENSE_HOTSPOT || profile == ScenarioWorldProfile.LUNCH_PEAK) {
            return HCM_HOTSPOTS.get(index % 2);
        }
        if (profile == ScenarioWorldProfile.DINNER_PEAK) {
            return HCM_HOTSPOTS.get((index % 3) + 1);
        }
        return HCM_HOTSPOTS.get(Math.floorMod(index + random.nextInt(HCM_HOTSPOTS.size()), HCM_HOTSPOTS.size()));
    }

    private static double jitter(double base, Random random, double amplitude) {
        return base + ((random.nextDouble() * 2.0) - 1.0) * amplitude;
    }

    public enum ScenarioWorldProfile {
        NORMAL_CLEAR(WeatherProfile.CLEAR, BASE_DECISION_TIME, 0.020, 0.028, 0.012, 0.018, 0.004, 20, 15, 18, 90, 7),
        HEAVY_RAIN(WeatherProfile.HEAVY_RAIN, Instant.parse("2026-04-16T11:30:00Z"), 0.016, 0.024, 0.010, 0.016, 0.003, 24, 12, 16, 120, 6),
        TRAFFIC_SHOCK(WeatherProfile.CLEAR, Instant.parse("2026-04-16T08:00:00Z"), 0.018, 0.026, 0.011, 0.017, 0.0035, 22, 14, 16, 90, 7),
        LUNCH_PEAK(WeatherProfile.CLEAR, Instant.parse("2026-04-16T05:30:00Z"), 0.012, 0.022, 0.009, 0.014, 0.0025, 18, 10, 10, 75, 5),
        DINNER_PEAK(WeatherProfile.CLEAR, Instant.parse("2026-04-16T10:30:00Z"), 0.013, 0.024, 0.010, 0.016, 0.0025, 18, 10, 12, 75, 5),
        DENSE_HOTSPOT(WeatherProfile.CLEAR, BASE_DECISION_TIME, 0.010, 0.020, 0.008, 0.013, 0.002, 19, 9, 12, 75, 5),
        DENSE_BUNDLE_DEMO(WeatherProfile.CLEAR, BASE_DECISION_TIME, 0.004, 0.009, 0.006, 0.004, 0.0015, 24, 4, 5, 45, 6);

        private final WeatherProfile weatherProfile;
        private final Instant decisionTime;
        private final double pickupAmplitude;
        private final double dropAmplitude;
        private final double dropOffset;
        private final double driverAmplitude;
        private final double driverOffset;
        private final int baseReadyWindowMinutes;
        private final int readyWindowSpread;
        private final int readyBucketSpan;
        private final int readyStepSeconds;
        private final int priorityInterval;

        ScenarioWorldProfile(WeatherProfile weatherProfile,
                             Instant decisionTime,
                             double pickupAmplitude,
                             double dropAmplitude,
                             double dropOffset,
                             double driverAmplitude,
                             double driverOffset,
                             int baseReadyWindowMinutes,
                             int readyWindowSpread,
                             int readyBucketSpan,
                             int readyStepSeconds,
                             int priorityInterval) {
            this.weatherProfile = weatherProfile;
            this.decisionTime = decisionTime;
            this.pickupAmplitude = pickupAmplitude;
            this.dropAmplitude = dropAmplitude;
            this.dropOffset = dropOffset;
            this.driverAmplitude = driverAmplitude;
            this.driverOffset = driverOffset;
            this.baseReadyWindowMinutes = baseReadyWindowMinutes;
            this.readyWindowSpread = readyWindowSpread;
            this.readyBucketSpan = readyBucketSpan;
            this.readyStepSeconds = readyStepSeconds;
            this.priorityInterval = priorityInterval;
        }

        public WeatherProfile weatherProfile() {
            return weatherProfile;
        }

        public Instant decisionTime() {
            return decisionTime;
        }

        public double pickupAmplitude() {
            return pickupAmplitude;
        }

        public double dropAmplitude() {
            return dropAmplitude;
        }

        public double dropOffset() {
            return dropOffset;
        }

        public double driverAmplitude() {
            return driverAmplitude;
        }

        public double driverOffset() {
            return driverOffset;
        }

        public int baseReadyWindowMinutes() {
            return baseReadyWindowMinutes;
        }

        public int readyWindowSpread() {
            return readyWindowSpread;
        }

        public int readyBucketSpan() {
            return readyBucketSpan;
        }

        public int readyStepSeconds() {
            return readyStepSeconds;
        }

        public int priorityInterval() {
            return priorityInterval;
        }
    }
}
