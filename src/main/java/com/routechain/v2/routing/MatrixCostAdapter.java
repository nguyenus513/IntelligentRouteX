package com.routechain.v2.routing;

public final class MatrixCostAdapter {
    private final DistanceDurationMatrixSnapshot snapshot;

    public MatrixCostAdapter(DistanceDurationMatrixSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    public DistanceDurationMatrixSnapshot snapshot() {
        return snapshot;
    }

    public double distanceKm(String fromNodeId, String toNodeId) {
        return snapshot.distanceKm()[index(fromNodeId)][index(toNodeId)];
    }

    public double durationMinutes(String fromNodeId, String toNodeId) {
        return snapshot.durationMinutes()[index(fromNodeId)][index(toNodeId)];
    }

    public double distanceKm(double fromLat, double fromLng, double toLat, double toLng) {
        return snapshot.distanceKm()[coordinateIndex(fromLat, fromLng)][coordinateIndex(toLat, toLng)];
    }

    public double durationMinutes(double fromLat, double fromLng, double toLat, double toLng) {
        return snapshot.durationMinutes()[coordinateIndex(fromLat, fromLng)][coordinateIndex(toLat, toLng)];
    }

    private int index(String nodeId) {
        Integer index = snapshot.nodeIndex().get(nodeId);
        if (index == null) {
            throw new IllegalArgumentException("Missing matrix node: " + nodeId);
        }
        return index;
    }

    private int coordinateIndex(double lat, double lng) {
        String key = MatrixSnapshotBuilder.coordinateKey(lat, lng);
        Integer index = snapshot.coordinateIndex().get(key);
        if (index == null) {
            throw new IllegalArgumentException("Missing matrix coordinate: " + key);
        }
        return index;
    }
}
