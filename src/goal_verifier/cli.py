"""Command-line interface for Achilles-AI Version 0."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .capture import capture_command, record_static_evidence, utc_now
from .evidence import create_layout, list_evidence, load_plan, read_json, verification_path, write_json
from .git_state import capture_file_snapshot, capture_git_state
from .report import generate_reports
from .schema import (
    ASSESSMENTS,
    EXECUTABLE_TYPES,
    VERIFICATION_TYPES,
    SchemaError,
    validate_plan,
    validate_requirements,
)


def _root(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"repository root is not a directory: {path}")
    return path


def _load_object(path: str) -> Any:
    return read_json(Path(path).resolve())


def _empty_profile() -> dict[str, list[Any]]:
    return {
        "build_commands": [],
        "test_commands": [],
        "run_commands": [],
        "benchmark_commands": [],
        "relevant_paths": [],
        "discovered_from": [],
        "notes": [],
    }


def initialize(args: argparse.Namespace) -> int:
    root: Path = args.root
    directory = verification_path(root)
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"verification directory is not empty: {directory}")
    git_before = capture_git_state(root)
    files_before = capture_file_snapshot(root)
    create_layout(root)
    requirements = _load_object(args.requirements) if args.requirements else []
    validate_requirements(requirements)
    goal = args.goal or "Goal pending agent decomposition"
    plan = {
        "version": "0",
        "goal": goal,
        "created_at": utc_now(),
        "repository": {
            "root": str(root),
            "git_commit": git_before["commit"],
            "worktree_dirty": git_before["dirty"],
        },
        "requirements": requirements,
    }
    validate_plan(plan)
    profile = _load_object(args.profile) if args.profile else _empty_profile()
    if not isinstance(profile, dict):
        raise SchemaError("repo profile must be a JSON object")
    write_json(directory / "plan.json", plan)
    write_json(directory / "repo_profile.json", profile)
    write_json(
        directory / "session.json",
        {
            "version": "0",
            "initialized_at": utc_now(),
            "repository_before": git_before,
            "files_before": files_before,
        },
    )
    print(f"Initialized verification at {directory}")
    print(f"Requirements: {len(requirements)}")
    return 0


def run_command(args: argparse.Namespace) -> int:
    plan = load_plan(args.root)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    measurement = _load_object(args.measurement) if args.measurement else None
    if measurement is not None and not isinstance(measurement, dict):
        raise SchemaError("measurement must be a JSON object")
    cwd = args.root / args.cwd if args.cwd else args.root
    evidence = capture_command(
        root=args.root,
        plan=plan,
        requirement_id=args.requirement,
        obligation_id=args.obligation,
        verification_type=args.type,
        command=command,
        cwd=cwd,
        source=args.source,
        expected_exit_code=args.expect_exit_code,
        baseline=args.baseline,
        measurement=measurement,
    )
    print(f"Evidence {evidence['id']} recorded")
    print(f"status = {evidence['status']}")
    print(f"exit_code = {evidence['exit_code']}")
    print(f"assessment = {evidence['assessment']}")
    return 130 if evidence["status"] == "INTERRUPTED" else 0


def record(args: argparse.Namespace) -> int:
    plan = load_plan(args.root)
    evidence = record_static_evidence(
        root=args.root,
        plan=plan,
        requirement_id=args.requirement,
        obligation_id=args.obligation,
        verification_type=args.type,
        source_path=args.source,
        description=args.description,
        assessment=args.assessment,
        line=args.line,
    )
    print(f"Evidence {evidence['id']} recorded")
    print(f"assessment = {evidence['assessment']}")
    return 0


def report(args: argparse.Namespace) -> int:
    result = generate_reports(args.root, load_plan(args.root))
    print(f"Overall Verdict: {result['overall_verdict']}")
    print(
        "Requirements: "
        + ", ".join(f"{result['counts'][value]} {value}" for value in ("PASS", "FAIL", "PARTIAL", "UNKNOWN"))
    )
    print(f"Report: {verification_path(args.root) / 'report.md'}")
    return 0


def status(args: argparse.Namespace) -> int:
    plan = load_plan(args.root)
    evidence = list_evidence(args.root)
    report_path = verification_path(args.root) / "report.json"
    current_verdict = "NOT_GENERATED"
    if report_path.is_file():
        current_verdict = read_json(report_path).get("overall_verdict", "UNKNOWN")
    print(f"Goal: {plan['goal']}")
    print(f"Requirements: {len(plan['requirements'])}")
    print(f"Evidence: {len(evidence)}")
    print(f"Current verdict: {current_verdict}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify", description="Achilles-AI Version 0 evidence runtime")
    parser.add_argument("--root", type=_root, default=Path.cwd(), help="repository root (default: current directory)")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    init_parser = subparsers.add_parser("init", help="create .verification and its initial plan")
    init_parser.add_argument("--goal", help="natural-language goal")
    init_parser.add_argument("--requirements", help="JSON file containing structured requirements")
    init_parser.add_argument("--profile", help="JSON file containing discovered repository interfaces")
    init_parser.set_defaults(handler=initialize)

    run_parser = subparsers.add_parser("run", help="execute a command and persist executable evidence")
    run_parser.add_argument("--requirement", required=True)
    run_parser.add_argument("--obligation", required=True)
    run_parser.add_argument("--type", required=True, choices=sorted(EXECUTABLE_TYPES))
    run_parser.add_argument("--source", default="command", help="evidence origin, e.g. existing_test or generated_test")
    run_parser.add_argument("--cwd", help="command working directory relative to repository root")
    run_parser.add_argument("--expect-exit-code", type=int, help="explicit executable oracle; omit for inconclusive capture")
    run_parser.add_argument("--baseline", help="explicit baseline identity for DIFFERENTIAL evidence")
    run_parser.add_argument("--measurement", help="JSON metadata for PERFORMANCE evidence")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    run_parser.set_defaults(handler=run_command)

    record_parser = subparsers.add_parser("record", help="persist static, human, or unknown evidence")
    record_parser.add_argument("--requirement", required=True)
    record_parser.add_argument("--obligation", required=True)
    record_parser.add_argument("--type", required=True, choices=["STATIC", "HUMAN", "UNKNOWN"])
    record_parser.add_argument("--source", help="repository file path (required for STATIC)")
    record_parser.add_argument("--line", help="line or range, if known")
    record_parser.add_argument("--description", required=True)
    record_parser.add_argument("--assessment", required=True, choices=sorted(ASSESSMENTS))
    record_parser.set_defaults(handler=record)

    report_parser = subparsers.add_parser("report", help="assess obligations and generate report.json/report.md")
    report_parser.set_defaults(handler=report)

    status_parser = subparsers.add_parser("status", help="show goal, requirements, evidence count, and verdict")
    status_parser.set_defaults(handler=status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, FileExistsError, json.JSONDecodeError, SchemaError, OSError) as exc:
        print(f"verify: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
