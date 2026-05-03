from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "benchmark" / "full-system-e2e"
DEFAULT_VISUAL_ROOT = REPO_ROOT / "artifacts" / "visual" / "dispatch-v2" / "full-system-e2e"
DEFAULT_LLM_BASE_URL = "http://127.0.0.1:20128/v1"
DEFAULT_OSRM_BASE_URL = "http://127.0.0.1:5000"

WORKERS = {
    "tabular": 8091,
    "routefinder": 8092,
    "greedrl": 8093,
    "forecast": 8096,
}

SMOKE_MATRIX = (("normal-clear", "S"),)
CORE_MATRIX = (
    ("normal-clear", "S"),
    ("heavy-rain", "S"),
    ("traffic-shock", "S"),
    ("route-ambiguity", "S"),
    ("driver-scarcity", "S"),
    ("dinner-peak-high-density", "S"),
)
SUPPORTED_SCENARIOS = {
    "normal-clear",
    "heavy-rain",
    "traffic-shock",
    "forecast-heavy",
    "dense-bundle-20x5",
    "worker-degradation",
    "live-source-degradation",
}
MODE_ORDER = ("full-system", "no-llm", "no-heavy-ml", "ortools-baseline")


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    status_code: Optional[int]
    latency_ms: int
    body: str
    error: str = ""


@dataclass(frozen=True)
class BenchmarkCell:
    scenario: str
    size: str
    mode: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def http_get(url: str, timeout_seconds: float = 5.0) -> HttpResult:
    started = time.perf_counter()
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "IntelligentRouteX full-system-e2e"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            latency_ms = int((time.perf_counter() - started) * 1000)
            return HttpResult(True, response.getcode(), latency_ms, body)
    except urllib.error.HTTPError as exception:
        body = exception.read().decode("utf-8", errors="replace") if exception.fp else ""
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HttpResult(False, exception.code, latency_ms, body, str(exception))
    except Exception as exception:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HttpResult(False, None, latency_ms, "", str(exception))


def http_post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout_seconds: float = 20.0,
) -> HttpResult:
    started = time.perf_counter()
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": "IntelligentRouteX full-system-e2e",
    }
    request_headers.update(headers)
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            latency_ms = int((time.perf_counter() - started) * 1000)
            return HttpResult(True, response.getcode(), latency_ms, body)
    except urllib.error.HTTPError as exception:
        body = exception.read().decode("utf-8", errors="replace") if exception.fp else ""
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HttpResult(False, exception.code, latency_ms, body, str(exception))
    except Exception as exception:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return HttpResult(False, None, latency_ms, "", str(exception))


def parse_json_body(result: HttpResult) -> Dict[str, Any]:
    if not result.body.strip():
        return {}
    try:
        return json.loads(result.body)
    except json.JSONDecodeError:
        return {"rawBody": result.body[:500]}


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "ok", "ready"}
    return bool(value)


def worker_version_ready(version: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing = [
        key
        for key in ("device", "dtype", "gpuMemoryAllocatedMb", "batchSize", "compileMode")
        if key not in version
    ]
    if not truthy(version.get("modelLoaded")):
        missing.append("modelLoaded=true")
    if not truthy(version.get("warmupDone")):
        missing.append("warmupDone=true")
    return not missing, missing


def check_workers() -> Dict[str, Any]:
    rows = []
    all_ready = True
    for name, port in WORKERS.items():
        base_url = f"http://127.0.0.1:{port}"
        health = http_get(f"{base_url}/health", 30)
        ready = http_get(f"{base_url}/ready", 180)
        version_result = http_get(f"{base_url}/version", 180)
        ready_payload = parse_json_body(ready)
        version = parse_json_body(version_result)
        version_ok, missing = worker_version_ready(version)
        ready_ok = health.ok and ready.ok and version_result.ok and version_ok
        all_ready = all_ready and ready_ok
        rows.append(
            {
                "name": name,
                "port": port,
                "baseUrl": base_url,
                "ready": ready_ok,
                "readyReason": ready_payload.get("reason", ""),
                "readyPayload": ready_payload,
                "health": endpoint_result(health),
                "readyEndpoint": endpoint_result(ready),
                "versionEndpoint": endpoint_result(version_result),
                "version": version,
                "versionMissing": missing,
            }
        )
    return {"ready": all_ready, "workers": rows}


def endpoint_result(result: HttpResult) -> Dict[str, Any]:
    return {
        "ok": result.ok,
        "statusCode": result.status_code,
        "latencyMs": result.latency_ms,
        "error": result.error,
    }


def check_osrm(base_url: str) -> Dict[str, Any]:
    base_url = base_url.rstrip("/")
    health = http_get(f"{base_url}/health", 5)
    route = http_get(
        f"{base_url}/route/v1/driving/106.700,10.776;106.710,10.780"
        "?overview=full&geometries=polyline",
        10,
    )
    body = parse_json_body(route)
    route_ok = route.ok and body.get("code") == "Ok"
    return {
        "ready": bool(health.ok or route_ok),
        "health": endpoint_result(health),
        "routeProbe": {
            "ok": route_ok,
            "statusCode": route.status_code,
            "latencyMs": route.latency_ms,
            "code": body.get("code"),
            "error": route.error,
        },
    }


def build_llm_probe_payload(model: str) -> Dict[str, Any]:
    return {
        "model": model,
        "parallel_tool_calls": False,
        "reasoning": {"effort": "medium"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "provider_probe_v1",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
            }
        },
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Return exactly this JSON object: {\"ok\": true}",
                    }
                ],
            }
        ],
    }


def classify_llm_failure(result: HttpResult) -> str:
    if result.ok:
        return "accepted"
    body = result.body.lower()
    if result.status_code in (401, 403):
        return "provider-auth-error"
    if result.status_code in (400, 404, 422) and "model" in body:
        return "provider-model-unresolved"
    if result.status_code == 404:
        return "provider-endpoint-not-found"
    if result.status_code == 429:
        return "provider-rate-limited"
    if result.status_code is not None and result.status_code >= 500:
        return "provider-server-error"
    if "timeout" in result.error.lower() or "timed out" in result.error.lower():
        return "provider-timeout"
    return "provider-http-error" if result.status_code is not None else "provider-network-error"


def check_llm(base_url: str, models: Sequence[str], api_key_env: str) -> Dict[str, Any]:
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get(api_key_env, "")
    if not api_key.strip():
        return {
            "ready": False,
            "providerResponsesReady": False,
            "modelUsed": None,
            "modelResolutionFallbackUsed": False,
            "providerFailureClass": "provider-auth-error",
            "apiKeyEnv": api_key_env,
            "results": [
                {
                    "model": model,
                    "accepted": False,
                    "failureClass": "provider-auth-error",
                    "error": "missing API key",
                }
                for model in models
            ],
        }

    endpoint = base_url.rstrip("/") + "/responses"
    results = []
    for index, model in enumerate(models):
        result = http_post_json(endpoint, build_llm_probe_payload(model), {"Authorization": "Bearer " + api_key}, 20)
        body = parse_json_body(result)
        accepted = result.ok and bool(body)
        failure = "accepted" if accepted else classify_llm_failure(result)
        results.append(
            {
                "model": model,
                "accepted": accepted,
                "failureClass": failure,
                "statusCode": result.status_code,
                "latencyMs": result.latency_ms,
                "error": result.error,
            }
        )
        if accepted:
            return {
                "ready": True,
                "providerResponsesReady": True,
                "modelUsed": model,
                "modelResolutionFallbackUsed": index > 0,
                "providerFailureClass": "accepted",
                "apiKeyEnv": api_key_env,
                "results": results,
            }
    return {
        "ready": False,
        "providerResponsesReady": False,
        "modelUsed": None,
        "modelResolutionFallbackUsed": False,
        "providerFailureClass": results[-1]["failureClass"] if results else "provider-not-probed",
        "apiKeyEnv": api_key_env,
        "results": results,
    }


def run_preflight(args: argparse.Namespace) -> Dict[str, Any]:
    workers = check_workers()
    osrm = check_osrm(DEFAULT_OSRM_BASE_URL)
    llm = {
        "ready": False,
        "providerResponsesReady": False,
        "modelUsed": None,
        "modelResolutionFallbackUsed": False,
        "providerFailureClass": "llm-disabled-by-policy",
        "apiKeyEnv": args.llm_api_key_env,
        "results": [],
    }
    blockers = []
    if not workers["ready"]:
        blockers.append("LOCAL_ML_NOT_ATTACHED")
    if not osrm["ready"]:
        blockers.append("OSRM_NOT_READY")
    return {
        "schemaVersion": "full-system-e2e-preflight/v1",
        "generatedAt": utc_now(),
        "verdict": "PASS" if not blockers else blockers[0],
        "blockers": blockers,
        "workers": workers,
        "osrm": osrm,
        "llm": llm,
    }


def matrix_cells(matrix: str, modes: Sequence[str]) -> List[BenchmarkCell]:
    base = SMOKE_MATRIX if matrix == "preset:smoke" else CORE_MATRIX
    cells = []
    for scenario, size in base:
        actual = map_supported_scenario(scenario)
        for mode in modes:
            cells.append(BenchmarkCell(actual, size, mode))
    return cells


def map_supported_scenario(scenario: str) -> str:
    if scenario in SUPPORTED_SCENARIOS:
        return scenario
    if scenario == "route-ambiguity":
        return "forecast-heavy"
    if scenario in {"driver-scarcity", "dinner-peak-high-density"}:
        return "dense-bundle-20x5"
    return scenario


def gradle_command() -> List[str]:
    return [str(REPO_ROOT / "gradlew.bat")] if os.name == "nt" else [str(REPO_ROOT / "gradlew")]


def no_heavy_ml_system_properties(cell: BenchmarkCell) -> List[str]:
    if cell.mode != "no-heavy-ml":
        return []
    return [
        "-Droutechain.dispatch-v2.ml.routefinder.enabled=false",
        "-Droutechain.dispatch-v2.ml.greedrl.enabled=false",
        "-Droutechain.dispatch-v2.ml.forecast.enabled=false",
        "-Droutechain.dispatch-v2.compute.adaptive.routefinder-max-tuples-per-dispatch=0",
        "-Droutechain.dispatch-v2.compute.adaptive.forecast-enabled-in-hot-path-by-default=false",
    ]


def terminate_process_tree(process_id: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.kill(process_id, 9)
    except OSError:
        return


def mode_env(cell: BenchmarkCell, args: argparse.Namespace, output_dir: Path) -> Dict[str, str]:
    decision = "legacy"
    baseline = "C"
    if cell.mode == "ortools-baseline":
        baseline = "B"
    env = {
        "DISPATCH_QUALITY_BASELINES": baseline,
        "DISPATCH_QUALITY_SIZE": cell.size,
        "DISPATCH_QUALITY_SCENARIO_PACK": cell.scenario,
        "DISPATCH_QUALITY_DECISION_MODE": decision,
        "DISPATCH_QUALITY_PROMPT_FAMILY": args.prompt_family,
        "DISPATCH_QUALITY_EXECUTION_MODE": "local-real",
        "DISPATCH_QUALITY_AUTHORITY": "false",
        "DISPATCH_QUALITY_OUTPUT_DIR": str(output_dir),
        "DISPATCH_QUALITY_PROFILE": args.profile,
        "ROUTECHAIN_DECISION_LLM_MODEL": "disabled-by-policy",
        "ROUTECHAIN_DECISION_LLM_BASE_URL": "disabled-by-policy",
        "IRX_ROUTING_PROVIDER": args.routing_provider,
        "IRX_ROUTING_BASE_URL": DEFAULT_OSRM_BASE_URL,
        "IRX_TABULAR_BASE_URL": "http://127.0.0.1:8091",
        "IRX_ROUTEFINDER_BASE_URL": "http://127.0.0.1:8092",
        "IRX_GREEDRL_BASE_URL": "http://127.0.0.1:8093",
        "IRX_FORECAST_BASE_URL": "http://127.0.0.1:8096",
        "ROUTECHAIN_DISPATCH_V2_ML_GREEDRL_CONNECT_TIMEOUT": "2s",
        "ROUTECHAIN_DISPATCH_V2_ML_GREEDRL_READ_TIMEOUT": "30s",
        "ROUTECHAIN_DISPATCH_V2_ML_GREEDRL_BUNDLE_TIMEOUT": "30s",
        "ROUTECHAIN_DISPATCH_V2_ML_GREEDRL_SEQUENCE_TIMEOUT": "30s",
    }
    if cell.mode == "no-heavy-ml":
        env.update({
            "ROUTECHAIN_DISPATCH_V2_ML_ROUTEFINDER_ENABLED": "false",
            "ROUTECHAIN_DISPATCH_V2_ML_GREEDRL_ENABLED": "false",
            "ROUTECHAIN_DISPATCH_V2_ML_FORECAST_ENABLED": "false",
            "ROUTECHAIN_DISPATCH_V2_COMPUTE_ADAPTIVE_ROUTEFINDER_MAX_TUPLES_PER_DISPATCH": "0",
            "ROUTECHAIN_DISPATCH_V2_COMPUTE_ADAPTIVE_FORECAST_ENABLED_IN_HOT_PATH_BY_DEFAULT": "false",
        })
    return env


def run_benchmark_cell(cell: BenchmarkCell, args: argparse.Namespace, output_root: Path) -> Dict[str, Any]:
    mode_dir = output_root / "mode-comparison" / cell.mode / cell.scenario / cell.size
    mode_dir.mkdir(parents=True, exist_ok=True)
    command = gradle_command() + [
        "--no-daemon",
        "--rerun-tasks",
        "-Droutechain.dispatch-v2.ml.greedrl.connect-timeout=2s",
        "-Droutechain.dispatch-v2.ml.greedrl.read-timeout=30s",
        "-Droutechain.dispatch-v2.ml.greedrl.bundle-timeout=30s",
        "-Droutechain.dispatch-v2.ml.greedrl.sequence-timeout=30s",
        *no_heavy_ml_system_properties(cell),
        "test",
        "--tests",
        "com.routechain.v2.benchmark.DispatchQualityArtifactSmokeTest",
    ]
    env = os.environ.copy()
    env.update(mode_env(cell, args, mode_dir))
    started = time.perf_counter()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
        )
        return_code = process.wait(timeout=parse_duration_seconds(args.cell_timeout))
    except subprocess.TimeoutExpired:
        if process is not None:
            terminate_process_tree(process.pid)
        return {
            "scenario": cell.scenario,
            "size": cell.size,
            "mode": cell.mode,
            "returnCode": None,
            "runtimeMs": int((time.perf_counter() - started) * 1000),
            "artifactRoot": str(mode_dir),
            "verdict": "FAIL",
            "reasons": ["benchmark-cell-timeout"],
        }
    return {
        "scenario": cell.scenario,
        "size": cell.size,
        "mode": cell.mode,
        "returnCode": return_code,
        "runtimeMs": int((time.perf_counter() - started) * 1000),
        "artifactRoot": str(mode_dir),
        "verdict": "PASS" if return_code == 0 else "FAIL",
        "reasons": [] if return_code == 0 else ["gradle-benchmark-failed"],
    }


def collect_latest_metrics(cell_result: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(cell_result.get("artifactRoot", ""))
    if not root.exists():
        return {}
    candidates = sorted(root.glob("dispatch-quality*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return {}
    payload = read_json(candidates[0])
    metrics = payload.get("metrics") or payload.get("controlMetrics") or {}
    return {
        "sourceArtifact": str(candidates[0]),
        "mlAttachStatus": payload.get("mlAttachStatus"),
        "coveredOrderCount": metrics.get("coveredOrderCount"),
        "executedAssignmentCount": metrics.get("executedAssignmentCount"),
        "selectedSingleOrderCount": metrics.get("selectedSingleOrderCount"),
        "bundleSizeDistribution": {
            "2": metrics.get("selectedBundleSize2Count"),
            "3": metrics.get("selectedBundleSize3Count"),
            "4": metrics.get("selectedBundleSize4Count"),
            "5": metrics.get("selectedBundleSize5Count"),
        },
        "workerFallbackRate": metrics.get("workerFallbackRate"),
        "routeFallbackRate": metrics.get("routeFallbackRate"),
        "objectiveValue": metrics.get("selectorObjectiveValue"),
    }


def write_preflight_report(output_root: Path, preflight: Dict[str, Any]) -> None:
    lines = [
        "# Full System E2E Preflight Report",
        "",
        f"- verdict: `{preflight['verdict']}`",
        f"- blockers: `{preflight.get('blockers', [])}`",
        "",
        "## ML Workers",
        "",
        "| worker | ready | reason | health | ready endpoint | version | missing |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for worker in preflight["workers"]["workers"]:
        lines.append(
            "| `{name}` | `{ready}` | `{reason}` | `{health}` | `{ready_endpoint}` | `{version}` | `{missing}` |".format(
                name=worker["name"],
                ready=worker["ready"],
                reason=worker.get("readyReason", ""),
                health=worker["health"]["ok"],
                ready_endpoint=worker["readyEndpoint"]["ok"],
                version=worker["versionEndpoint"]["ok"],
                missing=worker["versionMissing"],
            )
        )
    lines.extend(
        [
            "",
            "## OSRM",
            "",
            f"- ready: `{preflight['osrm']['ready']}`",
            f"- route code: `{preflight['osrm']['routeProbe'].get('code')}`",
            "",
            "## LLM",
            "",
            f"- ready: `{preflight['llm']['ready']}`",
            f"- modelUsed: `{preflight['llm'].get('modelUsed')}`",
            f"- fallbackUsed: `{preflight['llm'].get('modelResolutionFallbackUsed')}`",
            f"- providerFailureClass: `{preflight['llm'].get('providerFailureClass')}`",
        ]
    )
    (output_root / "preflight_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_final_report(output_root: Path, payload: Dict[str, Any]) -> None:
    lines = [
        "# Full System E2E Report",
        "",
        f"- verdict: `{payload.get('verdict')}`",
        f"- generatedAt: `{payload.get('generatedAt')}`",
        "",
        "| Case | Mode | Covered | Assignments | Bundle Dist | Bad Routes | Runtime | LLM Fallback | ML Fallback | Verdict |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload.get("results", []):
        metrics = row.get("metrics", {})
        lines.append(
            "| `{case}` | `{mode}` | `{covered}` | `{assignments}` | `{bundle}` | `{bad}` | `{runtime}` | `{llm}` | `{ml}` | `{verdict}` |".format(
                case=f"{row.get('scenario')}/{row.get('size')}",
                mode=row.get("mode"),
                covered=metrics.get("coveredOrderCount"),
                assignments=metrics.get("executedAssignmentCount"),
                bundle=metrics.get("bundleSizeDistribution", {}),
                bad=metrics.get("badRoadRouteCount", ""),
                runtime=row.get("runtimeMs", ""),
                llm=metrics.get("llmFallbackCount", ""),
                ml=metrics.get("workerFallbackRate", ""),
                verdict=row.get("verdict"),
            )
        )
    (output_root / "full_system_e2e_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_modes(raw: str) -> List[str]:
    modes = [part.strip() for part in raw.split(",") if part.strip()]
    unsupported = [mode for mode in modes if mode not in MODE_ORDER]
    if unsupported:
        raise ValueError("Unsupported compare mode(s): " + ",".join(unsupported))
    return modes


def parse_duration_seconds(raw: str) -> int:
    value = raw.strip().lower()
    if value.endswith("ms"):
        return max(1, int(float(value[:-2]) / 1000.0))
    if value.endswith("s"):
        return max(1, int(float(value[:-1])))
    if value.endswith("m"):
        return max(1, int(float(value[:-1]) * 60))
    return max(1, int(float(value)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 full-system E2E evaluation.")
    parser.add_argument("--matrix", choices=("preset:smoke", "preset:core"), default="preset:smoke")
    parser.add_argument("--profile", default="dispatch-v2-full-adaptive")
    parser.add_argument("--prompt-family", default="v3")
    parser.add_argument("--llm", choices=("off",), default="off")
    parser.add_argument("--ml", choices=("local-real",), default="local-real")
    parser.add_argument("--selector", choices=("ortools",), default="ortools")
    parser.add_argument("--routing-provider", choices=("osrm",), default="osrm")
    parser.add_argument("--compare-modes", default="full-system,no-llm,no-heavy-ml,ortools-baseline")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--visual-output-root", default=str(DEFAULT_VISUAL_ROOT))
    parser.add_argument("--llm-base-url", default="disabled-by-policy")
    parser.add_argument("--llm-model", default="disabled-by-policy")
    parser.add_argument("--llm-fallback-model", default="disabled-by-policy")
    parser.add_argument("--llm-api-key-env", default=os.environ.get("ROUTECHAIN_DECISION_LLM_API_KEY_ENV", "OPENAI_API_KEY"))
    parser.add_argument("--cell-timeout", default="12m")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    modes = parse_modes(args.compare_modes)
    preflight = run_preflight(args)
    write_json(output_root / "preflight_result.json", preflight)
    write_preflight_report(output_root, preflight)

    if preflight["verdict"] != "PASS" or args.preflight_only:
        payload = {
            "schemaVersion": "full-system-e2e-results/v1",
            "generatedAt": utc_now(),
            "verdict": preflight["verdict"],
            "preflight": preflight,
            "results": [],
        }
        write_json(output_root / "full_system_e2e_results.json", payload)
        write_final_report(output_root, payload)
        print(f"[FULL SYSTEM E2E] preflight verdict={preflight['verdict']}")
        print(f"[FULL SYSTEM E2E REPORT] {output_root / 'full_system_e2e_report.md'}")
        return 0 if args.preflight_only else 2

    results = []
    for cell in matrix_cells(args.matrix, modes):
        row = run_benchmark_cell(cell, args, output_root)
        row["metrics"] = collect_latest_metrics(row)
        metrics = row["metrics"]
        fail_reasons = []
        limit_reasons = []
        if metrics:
            if (metrics.get("coveredOrderCount") or 0) <= 0:
                fail_reasons.append("covered-order-count-zero")
            if (metrics.get("executedAssignmentCount") or 0) <= 0:
                fail_reasons.append("executed-assignment-count-zero")
            if metrics.get("mlAttachStatus") not in (None, "FULL_ATTACH"):
                limit_reasons.append(f"ml-attach-status-{metrics.get('mlAttachStatus')}")
            if (metrics.get("routeFallbackRate") or 0.0) > 0.0:
                fail_reasons.append("route-fallback-used")
        elif row.get("verdict") == "PASS":
            fail_reasons.append("quality-artifact-missing")
        if fail_reasons:
            row["verdict"] = "FAIL"
            row["reasons"] = list(row.get("reasons", [])) + fail_reasons + limit_reasons
        elif limit_reasons and row.get("verdict") == "PASS":
            row["verdict"] = "PASS_WITH_LIMITS"
            row["reasons"] = list(row.get("reasons", [])) + limit_reasons
        results.append(row)

    if any(row.get("verdict") == "FAIL" for row in results):
        verdict = "FAIL"
    elif all(row.get("verdict") == "PASS" for row in results):
        verdict = "PASS"
    else:
        verdict = "PASS_WITH_LIMITS"
    payload = {
        "schemaVersion": "full-system-e2e-results/v1",
        "generatedAt": utc_now(),
        "verdict": verdict,
        "preflight": preflight,
        "results": results,
    }
    write_json(output_root / "full_system_e2e_results.json", payload)
    write_final_report(output_root, payload)
    print(f"[FULL SYSTEM E2E] verdict={verdict}")
    print(f"[FULL SYSTEM E2E REPORT] {output_root / 'full_system_e2e_report.md'}")
    return 0 if verdict in {"PASS", "PASS_WITH_LIMITS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
