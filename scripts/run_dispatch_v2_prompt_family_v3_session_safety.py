from __future__ import annotations

import argparse
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation" / "prompt-family-v3" / "session-safety"
DEFAULT_TEST_RESULTS_DIR = REPO_ROOT / "build" / "test-results" / "test"
TEST_CLASS = "com.routechain.v2.decision.DecisionSessionStoreSafetyTest"


def gradle_command() -> List[str]:
    return [str(REPO_ROOT / "gradlew.bat")] if os.name == "nt" else [str(REPO_ROOT / "gradlew")]


def git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        check=False,
        capture_output=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 and completed.stdout.strip() else "workspace"


def run_tests(runner=subprocess.run) -> int:
    completed = runner(
        gradle_command() + ["--no-daemon", "test", "--tests", TEST_CLASS],
        cwd=REPO_ROOT,
        text=True,
        check=False,
    )
    return int(completed.returncode)


def locate_test_report(test_results_dir: Path) -> Optional[Path]:
    candidates = sorted(test_results_dir.rglob(f"TEST-{TEST_CLASS}.xml"))
    return candidates[-1] if candidates else None


def parse_test_report(report_path: Path) -> dict:
    root = ET.fromstring(report_path.read_text(encoding="utf-8"))
    cases = []
    for testcase in root.findall("testcase"):
        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")
        if failure is not None or error is not None:
            status = "FAIL"
            detail = (failure or error).attrib.get("message", "")
        elif skipped is not None:
            status = "SKIP"
            detail = skipped.attrib.get("message", "")
        else:
            status = "PASS"
            detail = ""
        cases.append({
            "name": testcase.attrib.get("name", ""),
            "classname": testcase.attrib.get("classname", ""),
            "timeSeconds": float(testcase.attrib.get("time", "0") or 0),
            "status": status,
            "detail": detail,
        })
    overall = "PASS" if cases and all(case["status"] == "PASS" for case in cases) else "FAIL"
    return {"reportPath": str(report_path), "overallVerdict": overall, "cases": cases}


def markdown_report(payload: dict) -> str:
    lines = [
        "# V3 Session Safety Report",
        "",
        f"- generatedAt: `{payload['generatedAt']}`",
        f"- validationCommit: `{payload['validationCommit']}`",
        f"- rerunExecuted: `{payload['rerunExecuted']}`",
        f"- junitReport: `{payload['junitReportPath']}`",
        f"- overallVerdict: `{payload['overallVerdict']}`",
        "",
        "| test | status | seconds |",
        "|---|---|---:|",
    ]
    for case in payload["cases"]:
        lines.append(f"| `{case['name']}` | `{case['status']}` | {case['timeSeconds']:.3f} |")
    return "\n".join(lines).rstrip() + "\n"


def write_report(payload: dict, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"session-safety-validation-{timestamp}.json"
    markdown_path = output_dir / "session_safety_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(payload), encoding="utf-8")
    return json_path, markdown_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run v3 decision-session safety validation.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--test-results-dir", default=str(DEFAULT_TEST_RESULTS_DIR))
    parser.add_argument("--rerun-tests", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    print(f"[SESSION SAFETY] test-class={TEST_CLASS}")
    print(f"- output-dir={args.output_dir}")
    print(f"- test-results-dir={args.test_results_dir}")
    if args.dry_run:
        return 0

    rerun_executed = False
    if args.rerun_tests:
        rerun_executed = True
        exit_code = run_tests()
        if exit_code != 0:
            print(f"[TEST FAILED] exit={exit_code}")
            return exit_code

    report_path = locate_test_report(Path(args.test_results_dir))
    if report_path is None:
        print("[ERROR] junit report not found")
        return 1
    parsed = parse_test_report(report_path)
    payload = {
        "schemaVersion": "dispatch-prompt-family-v3-session-safety/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "validationCommit": git_commit(),
        "rerunExecuted": rerun_executed,
        "junitReportPath": parsed["reportPath"],
        "overallVerdict": parsed["overallVerdict"],
        "cases": parsed["cases"],
    }
    json_path, markdown_path = write_report(payload, Path(args.output_dir))
    print(f"[REPORT JSON] {json_path}")
    print(f"[REPORT MARKDOWN] {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
