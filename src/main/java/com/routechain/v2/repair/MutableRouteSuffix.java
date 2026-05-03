package com.routechain.v2.repair;

import java.util.List;

public record MutableRouteSuffix(
        List<String> stopOrder) {

    public MutableRouteSuffix {
        stopOrder = stopOrder == null ? List.of() : List.copyOf(stopOrder);
    }
}
