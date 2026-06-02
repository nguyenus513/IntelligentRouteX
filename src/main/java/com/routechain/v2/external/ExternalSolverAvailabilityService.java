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
        result.put("vroom", checkVroom(enabled));
        String portablePython = System.getenv("PYVRP_PYTHON");
        List<String> pyvrpCommand = portablePython != null && !portablePython.isBlank()
                ? List.of(portablePython, "-c", "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))")
                : List.of("py", "-3", "-c", "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))");
        result.put("pyvrp", check("pyvrp", enabled, pyvrpCommand, "pyvrp-runtime-not-configured"));
        if (enabled) {
            enabledCache = Map.copyOf(result);
            return enabledCache;
        }
        disabledCache = Map.copyOf(result);
        return disabledCache;
    }

    private ExternalSolverAvailability checkVroom(boolean enabled) {
        if (!enabled) {
            return new ExternalSolverAvailability("vroom", ExternalContributorStatus.DISABLED, "disabled-in-fast-gate", "", Map.of("supportedModes", List.of("VROOM_BASE_URL", "VROOM_BIN")));
        }
        String baseUrl = System.getenv("VROOM_BASE_URL");
        if (baseUrl != null && !baseUrl.isBlank()) {
            return new ExternalSolverAvailability("vroom", ExternalContributorStatus.OK, "available-http", baseUrl, Map.of("mode", "HTTP", "baseUrl", baseUrl));
        }
        String bin = System.getenv("VROOM_BIN");
        if (bin != null && !bin.isBlank()) {
            return check("vroom", true, List.of(bin, "--version"), "vroom-runtime-not-configured");
        }
        return check("vroom", true, List.of("vroom", "--version"), "vroom-runtime-not-configured");
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
