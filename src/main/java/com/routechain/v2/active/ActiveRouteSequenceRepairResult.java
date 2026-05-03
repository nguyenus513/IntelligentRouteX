package com.routechain.v2.active;

import com.routechain.v2.SchemaVersioned;

import java.util.List;

public record ActiveRouteSequenceRepairResult(
        String schemaVersion,
        List<ActiveRouteStop> stopSequence,
        int movesTried,
        int movesAccepted,
        double distanceDelta,
        List<String> reasons) implements SchemaVersioned {

    public ActiveRouteSequenceRepairResult {
        stopSequence = stopSequence == null ? List.of() : List.copyOf(stopSequence);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
    }
}
