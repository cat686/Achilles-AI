"""Command-line interface for sealed Achilles-AI artifact schema v1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .capture_v1 import capture_command, record_static_evidence, utc_now
from .evidence import (
    create_layout,
    list_evidence_with_errors,
    load_plan,
    load_profile,
    read_json,
    verification_path,
    write_json,
)
from .git_state import capture_file_snapshot, capture_git_state
from .report_v1 import generate_reports, verification_state
from .schema_v1 import ASSESSMENTS, CURRENT_VERSION, LEGACY_VERSION, SchemaError, validate_profile, validate_requirements
from .sealing import load_seal, seal_verification


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
    profile = _load_object(args.profile) if args.profile else _empty_profile()
    validate_profile(profile)
    plan = {
        "version": CURRENT_VERSION,
        "goal": args.goal or "Goal pending agent decomposition",
        "created_at": utc_now(),
        "repository": {
            "root": str(root),
            "git_commit": git_before["commit"],
            "worktree_dirty": git_before["dirty"],
        },
        "requirements": requirements,
    }
    write_json(directory / "plan.json", plan)
    write_json(directory / "repo_profile.json", profile)
    write_json(
        directory / "session.json",
        {
            "version": CURRENT_VERSION,
            "initialized_at": utc_now(),
            "repository_before": git_before,
            "files_before": files_before,
        },
    )
    print(f"Initialized unsealed verification at {directory}")
    print(f"Requirements: {len(requirements)}")
    print("Complete the plan and generated tests, then run 'verify seal'.")
    return 0


def seal_command(args: argparse.Namespace) -> int:
    plan = load_plan(args.root)
    profile = load_profile(args.root)
    seal, created = seal_verification(args.root, plan, profile)
    print(f"Verification {'sealed' if created else 'already sealed'}: {seal['session_id']}")
    print(f"Summary: {verification_path(args.root) / 'seal-summary.md'}")
    return 0


def run_command(args: argparse.Namespace) -> int:
    plan = load_plan(args.root)
    evidence = capture_command(
        root=args.root,
        plan=plan,
        profile=load_profile(args.root),
        seal=load_seal(args.root),
        requirement_id=args.requirement,
        obligation_id=args.obligation,
    )
    print(f"Evidence {evidence['id']} recorded")
    print(f"status = {evidence['status']}")
    print(f"exit_code = {evidence['exit_code']}")
    print(f"assessment = {evidence['assessment']}")
    return 130 if evidence["status"] == "INTERRUPTED" else 0


def record(args: argparse.Namespace) -> int:
    evidence = record_static_evidence(
        root=args.root,
        plan=load_plan(args.root),
        profile=load_profile(args.root),
        seal=load_seal(args.root),
        requirement_id=args.requirement,
        obligation_id=args.obligation,
        description=args.description,
        assessment=args.assessment,
    )
    print(f"Evidence {evidence['id']} recorded")
    print(f"assessment = {evidence['assessment']}")
    return 0


def report(args: argparse.Namespace) -> int:
    result = generate_reports(args.root, load_plan(args.root, allow_legacy=True))
    print(f"Overall Verdict: {result['overall_verdict']}")
    print(f"Verification state: {result['verification_state']}")
    print(
        "Requirements: "
        + ", ".join(f"{result['counts'][value]} {value}" for value in ("PASS", "FAIL", "PARTIAL", "UNKNOWN"))
    )
    print(f"Report: {verification_path(args.root) / 'report.md'}")
    return 0


def status(args: argparse.Namespace) -> int:
    plan = load_plan(args.root, allow_legacy=True)
    evidence, errors = list_evidence_with_errors(args.root, allow_legacy=plan.get("version") == LEGACY_VERSION)
    state, inputs_digest, issues = verification_state(
        args.root, plan, None if plan.get("version") == LEGACY_VERSION else load_profile(args.root)
    )
    current_verdict = "UNKNOWN" if state in {"LEGACY", "UNSEALED", "STALE"} else "NOT_GENERATED"
    report_path = verification_path(args.root) / "report.json"
    if state == "SEALED" and report_path.is_file():
        saved = read_json(report_path)
        if saved.get("inputs_digest") == inputs_digest and saved.get("verification_state") == "SEALED":
            current_verdict = saved.get("overall_verdict", "UNKNOWN")
        else:
            state = "STALE"
            current_verdict = "UNKNOWN"
            issues.append("report inputs no longer match the sealed verification")
    print(f"Goal: {plan.get('goal', 'Legacy verification')}")
    print(f"State: {state}")
    print(f"Requirements: {len(plan.get('requirements', []))}")
    print(f"Evidence: {len(evidence) + len(errors)}")
    print(f"Current verdict: {current_verdict}")
    if issues:
        print("Issues: " + "; ".join(dict.fromkeys(issues)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify", description="Achilles-AI sealed evidence runtime")
    parser.add_argument("--root", type=_root, default=Path.cwd(), help="repository root (default: current directory)")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    init_parser = subparsers.add_parser("init", help="create an unsealed v1 verification workspace")
    init_parser.add_argument("--goal", help="natural-language goal")
    init_parser.add_argument("--requirements", help="JSON file containing v1 structured requirements")
    init_parser.add_argument("--profile", help="JSON file containing discovered repository interfaces")
    init_parser.set_defaults(handler=initialize)

    seal_parser = subparsers.add_parser("seal", help="freeze plan, commands, oracles, artifacts, and repository state")
    seal_parser.set_defaults(handler=seal_command)

    run_parser = subparsers.add_parser("run", help="execute the sealed experiment for an obligation")
    run_parser.add_argument("--requirement", required=True)
    run_parser.add_argument("--obligation", required=True)
    run_parser.set_defaults(handler=run_command)

    record_parser = subparsers.add_parser("record", help="record sealed static, human, or unknown evidence")
    record_parser.add_argument("--requirement", required=True)
    record_parser.add_argument("--obligation", required=True)
    record_parser.add_argument("--description", help="observation description; defaults to the sealed obligation")
    record_parser.add_argument("--assessment", required=True, choices=sorted(ASSESSMENTS))
    record_parser.set_defaults(handler=record)

    report_parser = subparsers.add_parser("report", help="validate the ledger and generate report.json/report.md")
    report_parser.set_defaults(handler=report)

    status_parser = subparsers.add_parser("status", help="show seal freshness, evidence count, and current verdict")
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
