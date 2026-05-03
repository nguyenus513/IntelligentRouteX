package com.routechain.v2.repair;

import com.routechain.v2.active.ActiveRouteInsertionCandidate;

public interface RepairOperatorStrategy {
    RepairSolution apply(ActiveRouteInsertionCandidate candidate);
}
