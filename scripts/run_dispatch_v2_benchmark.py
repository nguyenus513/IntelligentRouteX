import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "benchmark"
BASELINES = ("A", "B", "C")
SIZES = ("S", "M", "L", "XL")
SCENARIO_PACKS = (
    "normal-clear",
    "heavy-rain",
    "traffic-shock",
    "forecast-heavy",
    "worker-degradation",
    "live-source-degradation",
)
EXECUTION_MODES = ("controlled", "local-real")
DECISION_MODES = ("legacy", "llm-shadow", "llm-authoritative")
PROMPT_FAMILIES = ("v2", "v3")


@dataclass(frozen=True)
class BenchmarkCell:
    baselines: str
    size: str
    scenario_pack: str
    decision_mode: str
    prompt_family: str
    authoritative_stages: Tuple[str, ...]
    execution_mode: str
    authority: bool
    profile: str


@dataclass(frozen=True)
class CellArtifacts:
    json_paths: Tuple[Path, ...]
    markdown_paths: Tuple[Path, ...]
    csv_paths: Tuple[Path, ...]


def expand_selector(value: str, allowed: Sequence[str]) -> List[str]:
    if value == "all":
        return list(allowed)
    if value not in allowed:
        raise ValueError(f"Unsupported value '{value}'. Allowed: {', '.join(allowed)}")
    return [value]


def gradle_command() -> List[str]:
    return [str(REPO_ROOT / "gradlew.bat")] if os.name == "nt" else [str(REPO_ROOT / "gradlew")]


def cell_label(cell: BenchmarkCell) -> str:
    return (
        f"{cell.baselines}/{cell.size}/{cell.scenario_pack}/{cell.decision_mode}/"
        f"prompt-family={cell.prompt_family}/"
        f"stages={','.join(cell.authoritative_stages) if cell.authoritative_stages else 'default'}/"
        f"{cell.execution_mode}/authority={str(cell.authority).lower()}/"
        f"profile={cell.profile or 'default'}"
    )


def gradle_build_dir(output_dir: Path, cell: BenchmarkCell) -> Path:
    parts = [
        cell.scenario_pack,
        cell.size.lower(),
        cell.decision_mode,
        cell.prompt_family,
        cell.execution_mode,
        "authority" if cell.authority else "non-authority",
        cell.profile or "default",
    ]
    safe_parts = [part.replace("/", "-").replace("\\", "-").replace(":", "-") for part in parts]
    return output_dir.absolute().joinpath(".gradle-build", *safe_parts)


def planned_cells(args: argparse.Namespace) -> List[BenchmarkCell]:
    baseline_selector = "A,B,C" if args.baseline == "all" else args.baseline
    sizes = expand_selector(args.size, SIZES)
    scenario_packs = expand_selector(args.scenario_pack, SCENARIO_PACKS)
    decision_modes = expand_selector(args.decision_mode, DECISION_MODES)
    prompt_families = expand_selector(args.prompt_family, PROMPT_FAMILIES)
    execution_modes = expand_selector(args.execution_mode, EXECUTION_MODES)
    authoritative_stages = tuple(stage.strip() for stage in args.authoritative_stage if stage.strip())
    return [
        BenchmarkCell(baseline_selector, size, scenario_pack, decision_mode, prompt_family, authoritative_stages, execution_mode, args.authority, args.profile)
        for size in sizes
        for scenario_pack in scenario_packs
        for decision_mode in decision_modes
        for prompt_family in prompt_families
        for execution_mode in execution_modes
    ]


def run_cell(cell: BenchmarkCell, output_dir: Path, runner=subprocess.run, run_deferred_xl: bool = False):
    build_dir = gradle_build_dir(output_dir, cell)
    command = gradle_command() + [
        "--no-daemon",
        "--rerun-tasks",
        f"-PbuildDir={build_dir}",
        "test",
        "--tests",
        "com.routechain.v2.benchmark.DispatchQualityArtifactSmokeTest",
    ]
    env = os.environ.copy()
    env.update({
        "DISPATCH_QUALITY_BASELINES": cell.baselines,
        "DISPATCH_QUALITY_SIZE": cell.size,
        "DISPATCH_QUALITY_SCENARIO_PACK": cell.scenario_pack,
        "DISPATCH_QUALITY_DECISION_MODE": cell.decision_mode,
        "DISPATCH_QUALITY_PROMPT_FAMILY": cell.prompt_family,
        "DISPATCH_QUALITY_AUTHORITATIVE_STAGES": ",".join(cell.authoritative_stages),
        "DISPATCH_QUALITY_EXECUTION_MODE": cell.execution_mode,
        "DISPATCH_QUALITY_AUTHORITY": "true" if cell.authority else "false",
        "DISPATCH_QUALITY_OUTPUT_DIR": str(output_dir),
        "DISPATCH_QUALITY_RUN_DEFERRED_XL": "true" if run_deferred_xl else "false",
    })
    if cell.profile:
        env["DISPATCH_QUALITY_PROFILE"] = cell.profile
    return runner(command, cwd=REPO_ROOT, text=True, check=False, env=env)


def artifact_snapshot(output_dir: Path) -> CellArtifacts:
    if not output_dir.exists():
        return CellArtifacts((), (), ())
    json_paths = tuple(sorted(output_dir.glob("dispatch-quality*.json")))
    markdown_paths = tuple(sorted(output_dir.glob("dispatch-quality*.md")))
    csv_paths = tuple(sorted(output_dir.glob("dispatch-quality*.csv")))
    return CellArtifacts(json_paths, markdown_paths, csv_paths)


def artifact_delta(before: CellArtifacts, after: CellArtifacts) -> CellArtifacts:
    return CellArtifacts(
        tuple(path for path in after.json_paths if path not in before.json_paths),
        tuple(path for path in after.markdown_paths if path not in before.markdown_paths),
        tuple(path for path in after.csv_paths if path not in before.csv_paths),
    )


def artifact_paths_repr(paths: Sequence[Path]) -> str:
    if not paths:
        return "[]"
    return "[" + ", ".join(str(path) for path in paths) + "]"


def ensure_cell_artifacts(cell: BenchmarkCell, output_dir: Path, before: CellArtifacts, after: CellArtifacts, delta: CellArtifacts) -> None:
    if not delta.json_paths:
        raise RuntimeError(
            f"{cell_label(cell)} completed without new JSON artifacts "
            f"(output-root={output_dir} before-json={len(before.json_paths)} "
            f"after-json={len(after.json_paths)} new-json={artifact_paths_repr(delta.json_paths)})"
        )
    if not delta.markdown_paths:
        raise RuntimeError(
            f"{cell_label(cell)} completed without new Markdown artifacts "
            f"(output-root={output_dir} before-md={len(before.markdown_paths)} "
            f"after-md={len(after.markdown_paths)} new-md={artifact_paths_repr(delta.markdown_paths)})"
        )


def collect_results(output_dir: Path) -> List[dict]:
    if not output_dir.exists():
        return []
    results: List[dict] = []
    for path in sorted(output_dir.glob("dispatch-quality*.json")):
        with path.open("r", encoding="utf-8") as handle:
            results.append(json.load(handle))
    return results


def write_summary(results: Sequence[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "dispatch-quality-summary.md"
    lines = ["# Dispatch Quality Summary", "", f"- result count: `{len(results)}`", ""]
    for result in results:
        if "baselineId" in result:
            metrics = result.get("metrics", {})
            lines.extend([
                f"## `{result.get('scenarioPack')} / {result.get('baselineId')} / {result.get('workloadSize')}`",
                "",
                f"- decision mode: `{result.get('decisionMode', 'legacy')}`",
                f"- prompt family: `{result.get('promptFamily', 'v2')}`",
                f"- authoritative stages: `{result.get('authoritativeStages', [])}`",
                f"- execution mode: `{result.get('executionMode')}`",
                f"- authority class: `{result.get('runAuthorityClass', 'LOCAL_NON_AUTHORITY')}`",
                f"- authority eligible: `{result.get('authorityEligible', False)}`",
                f"- selected proposals: `{metrics.get('selectedProposalCount', 0)}`",
                f"- executed assignments: `{metrics.get('executedAssignmentCount', 0)}`",
                f"- robust utility average: `{metrics.get('robustUtilityAverage', 0.0)}`",
                f"- llm exact-match rate: `{result.get('llmShadowAgreement', {}).get('overallExactMatchRate', 0.0)}`",
                f"- token total: `{result.get('tokenUsageSummary', {}).get('totalTokens', 0)}`",
                f"- route geometry coverage: `{result.get('routeVectorMetrics', {}).get('geometryCoverage', 0.0)}`",
                "",
            ])
        elif "baselineResults" in result:
            lines.extend([
                f"## `comparison / {result.get('scenarioPack')} / {result.get('workloadSize')}`",
                "",
                f"- decision mode: `{result.get('decisionMode', 'legacy')}`",
                f"- prompt family: `{result.get('promptFamily', 'v2')}`",
                f"- authoritative stages: `{result.get('authoritativeStages', [])}`",
                f"- execution mode: `{result.get('executionMode')}`",
                f"- authority class: `{result.get('runAuthorityClass', 'LOCAL_NON_AUTHORITY')}`",
                f"- authority eligible: `{result.get('authorityEligible', False)}`",
                f"- summary: {result.get('comparisonSummary')}",
                "",
            ])
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dispatch V2 quality benchmark smoke scenarios.")
    parser.add_argument("--baseline", default="all", help="A|B|C|all")
    parser.add_argument("--size", default="all", help="S|M|L|XL|all")
    parser.add_argument("--scenario-pack", default="all", help="scenario pack or all")
    parser.add_argument("--decision-mode", default="legacy", help="legacy|llm-shadow|llm-authoritative|all")
    parser.add_argument("--prompt-family", default="v2", help="v2|v3|all")
    parser.add_argument("--authoritative-stage", action="append", default=[], help="Optional repeated authoritative stage override.")
    parser.add_argument("--execution-mode", default="controlled", help="controlled|local-real")
    parser.add_argument("--authority", action="store_true", help="Mark the run as authority-eligible when semantics allow it.")
    parser.add_argument("--profile", default="", help="Optional benchmark runtime profile, for example dispatch-v2-full-adaptive.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dry-run", action="store_true", help="Print the planned matrix only.")
    parser.add_argument("--run-deferred-xl", action="store_true", help="Run XL instead of serializing it as deferred.")
    args = parser.parse_args(argv)

    try:
        cells = planned_cells(args)
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 2

    output_dir = Path(args.output_dir)
    print(f"[MATRIX] {len(cells)} benchmark cell(s)")
    for cell in cells:
        print(
            f"- baselines={cell.baselines} size={cell.size} scenario-pack={cell.scenario_pack} "
            f"decision-mode={cell.decision_mode} prompt-family={cell.prompt_family} "
            f"authoritative-stages={list(cell.authoritative_stages)} "
            f"execution-mode={cell.execution_mode} authority={str(cell.authority).lower()} "
            f"profile={cell.profile or 'default'}"
        )
    if args.dry_run:
        return 0

    failures: List[str] = []
    for cell in cells:
        print(f"[CELL STARTED] {cell_label(cell)}")
        before = artifact_snapshot(output_dir)
        completed = run_cell(cell, output_dir, run_deferred_xl=args.run_deferred_xl)
        if completed.returncode != 0:
            failures.append(cell_label(cell))
            print(f"[CELL FAILED] {cell_label(cell)} returncode={completed.returncode}")
            continue
        after = artifact_snapshot(output_dir)
        try:
            delta = artifact_delta(before, after)
            ensure_cell_artifacts(cell, output_dir, before, after, delta)
            print(f"[CELL DISPATCH COMPLETED] {cell_label(cell)} returncode=0")
            summary_path = write_summary(collect_results(output_dir), output_dir)
            print(
                f"[CELL ARTIFACT WRITTEN] {cell_label(cell)} "
                f"json={len(delta.json_paths)} md={len(delta.markdown_paths)} csv={len(delta.csv_paths)}"
            )
            print(
                f"[CELL ARTIFACT PATHS] {cell_label(cell)} "
                f"output-root={output_dir} "
                f"json={artifact_paths_repr(delta.json_paths)} "
                f"md={artifact_paths_repr(delta.markdown_paths)} "
                f"csv={artifact_paths_repr(delta.csv_paths)}"
            )
            print(f"[CELL SUMMARY UPDATED] {summary_path}")
        except Exception as error:
            failures.append(cell_label(cell))
            print(f"[CELL FAILED] {cell_label(cell)} {error}")

    results = collect_results(output_dir)
    summary_path = write_summary(results, output_dir)
    print(f"[SUMMARY] wrote {len(results)} JSON artifact(s)")
    print(f"[SUMMARY] markdown summary: {summary_path}")
    if failures:
        print(f"[FAILURES] {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
