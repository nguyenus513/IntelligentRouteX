package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteStop;

import java.util.List;

public record FrozenRoutePrefix(
        List<ActiveRouteStop> stops) {

    public static FrozenRoutePrefix empty() {
        return new FrozenRoutePrefix(List.of());
    }
}
