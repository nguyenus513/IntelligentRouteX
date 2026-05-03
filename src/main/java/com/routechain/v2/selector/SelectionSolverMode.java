package com.routechain.v2.selector;

public enum SelectionSolverMode {
    GREEDY_INCUMBENT,
    GREEDY_REPAIR,
    ORTOOLS,
    CP_SAT_TIMEOUT_INCUMBENT,
    DEGRADED_GREEDY,
    MINI_EXACT
}
