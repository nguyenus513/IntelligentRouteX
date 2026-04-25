package com.routechain.v2.routing;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PickupDeliveryPermutationOptimizerTest {
    private final PickupDeliveryPermutationOptimizer optimizer = new PickupDeliveryPermutationOptimizer();

    @Test
    void choosesShortestValidPickupDropoffSequence() {
        RouteStop driver = stop("driver");
        List<PickupDeliveryStop> pickups = List.of(
                PickupDeliveryStop.pickup("order-1", stop("order-1:pickup")),
                PickupDeliveryStop.pickup("order-2", stop("order-2:pickup")));
        List<PickupDeliveryStop> dropoffs = List.of(
                PickupDeliveryStop.dropoff("order-1", stop("order-1:dropoff")),
                PickupDeliveryStop.dropoff("order-2", stop("order-2:dropoff")));
        MatrixBuilder matrix = new MatrixBuilder(driver, pickups, dropoffs);
        matrix.defaultDuration(999.0)
                .duration("driver", "order-2:pickup", 10.0)
                .duration("order-2:pickup", "order-1:pickup", 10.0)
                .duration("order-1:pickup", "order-1:dropoff", 10.0)
                .duration("order-1:dropoff", "order-2:dropoff", 10.0)
                .duration("driver", "order-1:pickup", 100.0)
                .duration("order-1:pickup", "order-2:pickup", 100.0)
                .direct("order-1", 10.0)
                .direct("order-2", 10.0);

        List<RouteSequence> sequences = optimizer.optimize(driver, pickups, dropoffs, matrix.build(), new RouteOptimizationConstraints(500.0, 5.0, 1));

        assertEquals(List.of("order-2:pickup", "order-1:pickup", "order-1:dropoff", "order-2:dropoff"), sequences.getFirst().stopIds());
        assertEquals(40.0, sequences.getFirst().totalDurationSeconds(), 1e-9);
        assertTrue(sequences.getFirst().feasible());
    }

    @Test
    void neverAllowsDropoffBeforePickup() {
        RouteStop driver = stop("driver");
        List<PickupDeliveryStop> pickups = List.of(PickupDeliveryStop.pickup("order-1", stop("order-1:pickup")));
        List<PickupDeliveryStop> dropoffs = List.of(PickupDeliveryStop.dropoff("order-1", stop("order-1:dropoff")));
        MatrixBuilder matrix = new MatrixBuilder(driver, pickups, dropoffs)
                .defaultDuration(5.0)
                .direct("order-1", 5.0);

        List<RouteSequence> sequences = optimizer.optimize(driver, pickups, dropoffs, matrix.build(), RouteOptimizationConstraints.defaults());

        assertEquals(List.of("order-1:pickup", "order-1:dropoff"), sequences.getFirst().stopIds());
    }

    @Test
    void marksHighDetourSequenceInfeasible() {
        RouteStop driver = stop("driver");
        List<PickupDeliveryStop> pickups = List.of(
                PickupDeliveryStop.pickup("order-1", stop("order-1:pickup")),
                PickupDeliveryStop.pickup("order-2", stop("order-2:pickup")));
        List<PickupDeliveryStop> dropoffs = List.of(
                PickupDeliveryStop.dropoff("order-1", stop("order-1:dropoff")),
                PickupDeliveryStop.dropoff("order-2", stop("order-2:dropoff")));
        MatrixBuilder matrix = new MatrixBuilder(driver, pickups, dropoffs)
                .defaultDuration(10.0)
                .direct("order-1", 10.0)
                .direct("order-2", 10.0)
                .duration("order-1:pickup", "order-2:pickup", 500.0)
                .duration("order-2:pickup", "order-1:dropoff", 500.0);

        List<RouteSequence> sequences = optimizer.optimize(driver, pickups, dropoffs, matrix.build(), new RouteOptimizationConstraints(2000.0, 0.50, 5));

        assertTrue(sequences.stream().anyMatch(sequence -> !sequence.feasible() && sequence.rejectReasons().contains("DETOUR_TOO_HIGH")));
    }

    @Test
    void prunesRoutesOverDurationLimit() {
        RouteStop driver = stop("driver");
        List<PickupDeliveryStop> pickups = List.of(PickupDeliveryStop.pickup("order-1", stop("order-1:pickup")));
        List<PickupDeliveryStop> dropoffs = List.of(PickupDeliveryStop.dropoff("order-1", stop("order-1:dropoff")));
        MatrixBuilder matrix = new MatrixBuilder(driver, pickups, dropoffs)
                .defaultDuration(1000.0)
                .direct("order-1", 1000.0);

        List<RouteSequence> sequences = optimizer.optimize(driver, pickups, dropoffs, matrix.build(), new RouteOptimizationConstraints(500.0, 10.0, 3));

        assertTrue(sequences.isEmpty());
    }

    @Test
    void skipsUnreachableMatrixCells() {
        RouteStop driver = stop("driver");
        List<PickupDeliveryStop> pickups = List.of(PickupDeliveryStop.pickup("order-1", stop("order-1:pickup")));
        List<PickupDeliveryStop> dropoffs = List.of(PickupDeliveryStop.dropoff("order-1", stop("order-1:dropoff")));
        MatrixBuilder matrix = new MatrixBuilder(driver, pickups, dropoffs)
                .defaultDuration(10.0)
                .duration("driver", "order-1:pickup", null)
                .direct("order-1", 10.0);

        List<RouteSequence> sequences = optimizer.optimize(driver, pickups, dropoffs, matrix.build(), RouteOptimizationConstraints.defaults());

        assertFalse(sequences.stream().anyMatch(RouteSequence::feasible));
    }

    private RouteStop stop(String id) {
        return new RouteStop(id, 10.0, 106.0, "test", "zone", 0.0);
    }

    private static final class MatrixBuilder {
        private final List<RouteStop> sources = new ArrayList<>();
        private final List<RouteStop> destinations = new ArrayList<>();
        private final Map<String, Double> durations = new HashMap<>();
        private double defaultDuration = 60.0;

        MatrixBuilder(RouteStop driver, List<PickupDeliveryStop> pickups, List<PickupDeliveryStop> dropoffs) {
            sources.add(driver);
            pickups.forEach(stop -> sources.add(stop.routeStop()));
            dropoffs.forEach(stop -> sources.add(stop.routeStop()));
            pickups.forEach(stop -> destinations.add(stop.routeStop()));
            dropoffs.forEach(stop -> destinations.add(stop.routeStop()));
        }

        MatrixBuilder defaultDuration(double value) {
            this.defaultDuration = value;
            return this;
        }

        MatrixBuilder direct(String orderId, Double duration) {
            return duration(orderId + ":pickup", orderId + ":dropoff", duration);
        }

        MatrixBuilder duration(String from, String to, Double duration) {
            durations.put(from + "->" + to, duration);
            return this;
        }

        DurationMatrix build() {
            List<List<Double>> durationRows = new ArrayList<>();
            List<List<Double>> distanceRows = new ArrayList<>();
            int nullCount = 0;
            for (RouteStop source : sources) {
                List<Double> durationRow = new ArrayList<>();
                List<Double> distanceRow = new ArrayList<>();
                for (RouteStop destination : destinations) {
                    Double value = durations.getOrDefault(source.stopId() + "->" + destination.stopId(), source.stopId().equals(destination.stopId()) ? 0.0 : defaultDuration);
                    if (value == null) {
                        nullCount++;
                        durationRow.add(null);
                        distanceRow.add(null);
                    } else {
                        durationRow.add(value);
                        distanceRow.add(value * 5.0);
                    }
                }
                durationRows.add(durationRow);
                distanceRows.add(distanceRow);
            }
            return new DurationMatrix("duration-matrix/v1", "test", sources, destinations, List.of(), List.of(), durationRows, distanceRows, nullCount, nullCount, 0, List.of());
        }
    }
}
