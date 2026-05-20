package com.routechain.v2.external;

import com.google.ortools.Loader;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public final class ExternalSolverRuntimeManager {
    private Map<String, ExternalSolverAvailability> cached;

    public synchronized Map<String, ExternalSolverAvailability> readiness() {
        if (cached != null) {
            return cached;
        }
        Map<String, ExternalSolverAvailability> result = new LinkedHashMap<>();
        result.put("vroom", checkVroom());
        result.put("ortools", checkOrtools());
        result.put("pyvrp", checkPyvrp());
        cached = Map.copyOf(result);
        return cached;
    }

    public boolean allReady() {
        return readiness().values().stream().allMatch(this::ready);
    }

    public boolean ready(String solverId) {
        ExternalSolverAvailability availability = readiness().get(solverId.toLowerCase(Locale.ROOT));
        return ready(availability);
    }

    public Map<String, String> compactStatus() {
        Map<String, String> status = new LinkedHashMap<>();
        readiness().forEach((key, value) -> status.put(key, ready(value) ? "AVAILABLE" : value.status().name()));
        return status;
    }

    private boolean ready(ExternalSolverAvailability availability) {
        return availability != null && availability.status() == ExternalContributorStatus.OK;
    }

    private ExternalSolverAvailability checkVroom() {
        String baseUrl = System.getenv("VROOM_BASE_URL");
        if (baseUrl != null && !baseUrl.isBlank()) {
            return new ExternalSolverAvailability("vroom", ExternalContributorStatus.OK, "available-http", baseUrl, Map.of("mode", "HTTP", "baseUrl", baseUrl));
        }
        String bin = System.getenv("VROOM_BIN");
        if (bin == null || bin.isBlank()) {
            Path bundled = Path.of("tools", "vroom", isWindows() ? "vroom-wsl.cmd" : "vroom");
            bin = Files.exists(bundled) ? bundled.toString() : "vroom";
        }
        return checkCommand("vroom", List.of(bin, "--version"), "VROOM_REQUIRED_BUT_NOT_AVAILABLE");
    }

    private ExternalSolverAvailability checkPyvrp() {
        List<String> command = isWindows()
                ? List.of("py", "-3", "-c", "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))")
                : List.of("python3", "-c", "import pyvrp; print(getattr(pyvrp, '__version__', 'unknown'))");
        return checkCommand("pyvrp", command, "PYVRP_REQUIRED_BUT_NOT_AVAILABLE");
    }

    private ExternalSolverAvailability checkOrtools() {
        try {
            Loader.loadNativeLibraries();
            return new ExternalSolverAvailability("ortools", ExternalContributorStatus.OK, "available-java", "ortools-java", Map.of("dependency", "com.google.ortools:ortools-java"));
        } catch (Throwable throwable) {
            return new ExternalSolverAvailability("ortools", ExternalContributorStatus.EVIDENCE_GAP, "ORTOOLS_REQUIRED_BUT_NOT_AVAILABLE", "", Map.of("error", throwable.getClass().getSimpleName()));
        }
    }

    private ExternalSolverAvailability checkCommand(String solverId, List<String> command, String reason) {
        try {
            Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
            boolean completed = process.waitFor(5, TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                return new ExternalSolverAvailability(solverId, ExternalContributorStatus.TIMEOUT, reason, "", Map.of("command", command));
            }
            String output = new String(process.getInputStream().readAllBytes()).trim();
            if (process.exitValue() == 0) {
                return new ExternalSolverAvailability(solverId, ExternalContributorStatus.OK, "available", output, Map.of("command", command));
            }
            return new ExternalSolverAvailability(solverId, ExternalContributorStatus.EVIDENCE_GAP, reason, output, Map.of("command", command, "exitCode", process.exitValue()));
        } catch (Exception exception) {
            return new ExternalSolverAvailability(solverId, ExternalContributorStatus.EVIDENCE_GAP, reason, "", Map.of("command", command, "error", exception.getClass().getSimpleName()));
        }
    }

    private boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win");
    }
}
