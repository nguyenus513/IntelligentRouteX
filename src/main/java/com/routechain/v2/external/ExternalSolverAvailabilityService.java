package com.routechain.v2.external;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ExternalSolverAvailabilityService {
    private Map<String, ExternalSolverAvailability> enabledCache;
    private Map<String, ExternalSolverAvailability> disabledCache;

    public Map<String, ExternalSolverAvailability> availability(boolean enabled) {
        if (enabled && enabledCache != null) {
            return enabledCache;
        }
        if (!enabled && disabledCache != null) {
            return disabledCache;
        }
        Map<String, ExternalSolverAvailability> result = new LinkedHashMap<>();
        result.put("vroom", check("vroom", enabled, List.of("vroom", "--version"), "vroom-runtime-not-configured"));
        result.put("pyvrp", check("pyvrp", enabled, List.of("py", "-3", "-c", "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))"), "pyvrp-runtime-not-configured"));
        if (enabled) {
            enabledCache = Map.copyOf(result);
            return enabledCache;
        }
        disabledCache = Map.copyOf(result);
        return disabledCache;
    }

    private ExternalSolverAvailability check(String solverId, boolean enabled, List<String> command, String evidenceGapReason) {
        if (!enabled) {
            return new ExternalSolverAvailability(solverId, ExternalContributorStatus.DISABLED, "disabled-in-fast-gate", "", Map.of("command", command));
        }
        ProcessBuilder builder = new ProcessBuilder(command);
        builder.redirectErrorStream(true);
        try {
            Process process = builder.start();
            boolean completed = process.waitFor(3, java.util.concurrent.TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                return new ExternalSolverAvailability(solverId, ExternalContributorStatus.TIMEOUT, "availability-check-timeout", "", Map.of("command", command));
            }
            String output = new String(process.getInputStream().readAllBytes()).trim();
            if (process.exitValue() == 0) {
                return new ExternalSolverAvailability(solverId, ExternalContributorStatus.OK, "available", output, Map.of("command", command));
            }
            return new ExternalSolverAvailability(solverId, ExternalContributorStatus.EVIDENCE_GAP, evidenceGapReason, output, Map.of("command", command, "exitCode", process.exitValue()));
        } catch (Exception exception) {
            return new ExternalSolverAvailability(solverId, ExternalContributorStatus.EVIDENCE_GAP, evidenceGapReason, "", Map.of("command", command, "error", exception.getClass().getSimpleName()));
        }
    }
}
