package com.routefood.app.core.map.routing;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class RouteQuality {
    public final String provider;
    public final double snapMaxDistanceMeters;
    public final boolean firstPointMatchesDriver;
    public final boolean coordinateOrderValidated;
    public final List<String> warnings;

    public RouteQuality(
            String provider,
            double snapMaxDistanceMeters,
            boolean firstPointMatchesDriver,
            boolean coordinateOrderValidated,
            List<String> warnings
    ) {
        this.provider = provider;
        this.snapMaxDistanceMeters = snapMaxDistanceMeters;
        this.firstPointMatchesDriver = firstPointMatchesDriver;
        this.coordinateOrderValidated = coordinateOrderValidated;
        this.warnings = Collections.unmodifiableList(new ArrayList<>(warnings));
    }

    public boolean healthy() {
        return firstPointMatchesDriver && coordinateOrderValidated && warnings.isEmpty();
    }
}
