from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation" / "llm-provider"
DEFAULT_BASE_URL = "https://r8cp2m4.9router.com/v1"
DEFAULT_MODELS = ("cx/gpt-5.5", "cx/gpt-5.4")
DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"


@dataclass(frozen=True)
class ProbeResult:
    model: str
    accepted: bool
    failure_class: str
    status_code: Optional[int]
    latency_ms: int
    schema_valid: bool
    response_hash: str
    error_summary: str


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def trim_trailing_slash(value: str) -> str:
    return value[:-1] if value.endswith("/") else value


def build_probe_payload(model: str) -> dict:
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


def classify_http_failure(status_code: int, body: str) -> str:
    normalized = (body or "").lower()
    if status_code in (401, 403):
        return "provider-auth-error"
    if status_code == 429:
        return "provider-rate-limited"
    if status_code == 408:
        return "provider-timeout"
    if status_code in (400, 404, 422) and "model" in normalized:
        return "provider-model-unresolved"
    if status_code >= 500:
        return "provider-http-5xx"
    if status_code >= 400:
        return "provider-http-4xx"
    return "provider-http-error"


def response_hash(body: str) -> str:
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def extract_output_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if isinstance(content_item, dict) and isinstance(content_item.get("text"), str):
                return content_item["text"]
    return ""


def schema_valid(body: str) -> bool:
    if not body or not body.strip():
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    text = extract_output_text(payload)
    if not text:
        return False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and parsed.get("ok") is True


def default_sender(url: str, api_key: str, timeout_seconds: float, payload: dict) -> Tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "IntelligentRouteX/dispatch-v2-provider-probe",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return int(error.code), error.read().decode("utf-8", errors="replace")
    except TimeoutError:
        raise TimeoutError("provider-timeout")
    except OSError as error:
        raise ConnectionError(str(error)) from error


def probe_model(
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
    sender: Callable[[str, str, float, dict], Tuple[int, str]] = default_sender,
) -> ProbeResult:
    url = trim_trailing_slash(base_url) + "/responses"
    started = time.perf_counter()
    try:
        status_code, body = sender(url, api_key, timeout_seconds, build_probe_payload(model))
    except TimeoutError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ProbeResult(model, False, "provider-timeout", None, latency_ms, False, "", "request timed out")
    except ConnectionError as error:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ProbeResult(model, False, "provider-http-error", None, latency_ms, False, "", str(error)[:160])
    latency_ms = int((time.perf_counter() - started) * 1000)
    body_hash = response_hash(body)
    if status_code >= 400:
        return ProbeResult(model, False, classify_http_failure(status_code, body), status_code, latency_ms, False, body_hash, "http failure")
    if not body or not body.strip():
        return ProbeResult(model, False, "provider-empty-response", status_code, latency_ms, False, body_hash, "empty response")
    if not schema_valid(body):
        return ProbeResult(model, False, "provider-schema-invalid", status_code, latency_ms, False, body_hash, "response schema invalid")
    return ProbeResult(model, True, "accepted", status_code, latency_ms, True, body_hash, "")


def result_to_dict(result: ProbeResult) -> dict:
    return {
        "model": result.model,
        "accepted": result.accepted,
        "failureClass": result.failure_class,
        "statusCode": result.status_code,
        "latencyMs": result.latency_ms,
        "schemaValid": result.schema_valid,
        "responseHash": result.response_hash,
        "errorSummary": result.error_summary,
    }


def write_artifacts(payload: dict, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"responses_probe-{timestamp}.json"
    markdown_path = output_dir / "responses_probe_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# LLM Provider Responses Probe",
        "",
        f"- generatedAt: `{payload['generatedAt']}`",
        f"- baseUrl: `{payload['baseUrl']}`",
        f"- selectedModel: `{payload.get('selectedModel') or 'none'}`",
        f"- ready: `{payload['ready']}`",
        "",
        "| model | accepted | failure class | status | latency ms | schema valid |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for result in payload["results"]:
        lines.append(
            f"| `{result['model']}` | `{result['accepted']}` | `{result['failureClass']}` | "
            f"`{result['statusCode']}` | `{result['latencyMs']}` | `{result['schemaValid']}` |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def run_probe(base_url: str, api_key: str, models: Sequence[str], timeout_seconds: float) -> dict:
    results = []
    selected_model = None
    for model in models:
        result = probe_model(base_url, api_key, model, timeout_seconds)
        results.append(result_to_dict(result))
        if result.accepted and selected_model is None:
            selected_model = model
            break
    return {
        "schemaVersion": "llm-provider-responses-probe/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": base_url,
        "modelsProbed": list(models),
        "selectedModel": selected_model,
        "ready": selected_model is not None,
        "results": results,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Probe an OpenAI-compatible /responses provider before prompt validation.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--api-key-env", default=os.environ.get("ROUTECHAIN_DECISION_LLM_API_KEY_ENV", DEFAULT_API_KEY_ENV))
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dotenv", default=str(REPO_ROOT / ".env"))
    args = parser.parse_args(argv)

    load_dotenv(Path(args.dotenv))
    base_url = args.base_url or os.environ.get("ROUTECHAIN_DECISION_LLM_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get(args.api_key_env, "")
    models = tuple(args.model or DEFAULT_MODELS)
    if not api_key.strip():
        payload = {
            "schemaVersion": "llm-provider-responses-probe/v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "baseUrl": base_url,
            "modelsProbed": list(models),
            "selectedModel": None,
            "ready": False,
            "results": [{
                "model": model,
                "accepted": False,
                "failureClass": "provider-auth-error",
                "statusCode": None,
                "latencyMs": 0,
                "schemaValid": False,
                "responseHash": "",
                "errorSummary": f"missing API key env {args.api_key_env}",
            } for model in models],
        }
    else:
        payload = run_probe(base_url, api_key, models, args.timeout_seconds)
    json_path, markdown_path = write_artifacts(payload, Path(args.output_dir))
    print(f"[RESPONSES PROBE JSON] {json_path}")
    print(f"[RESPONSES PROBE MARKDOWN] {markdown_path}")
    print(f"[RESPONSES PROBE READY] {str(payload['ready']).lower()} selectedModel={payload.get('selectedModel') or 'none'}")
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
