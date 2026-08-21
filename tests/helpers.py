from __future__ import annotations

from pathlib import Path
from typing import Any
import sys

from goal_verifier.capture import utc_now
from goal_verifier.evidence import create_layout, write_json
from goal_verifier.git_state import capture_file_snapshot, capture_git_state
from goal_verifier.sealing import seal_verification


def obligation(
    obligation_id: str = "R1-O1",
    verification_type: str = "TEST",
    mandatory: bool = True,
    *,
    argv: list[str] | None = None,
    oracle: dict[str, Any] | None = None,
    source: str = "existing_test",
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": obligation_id,
        "type": verification_type,
        "mandatory": mandatory,
        "description": f"Verify {obligation_id}",
        "planned_experiment": "Run a requirement-derived experiment",
    }
    if verification_type in {"BUILD", "TEST", "RUNTIME", "DIFFERENTIAL", "PERFORMANCE"}:
        value["experiment"] = {
            "argv": argv or [sys.executable, "-B", "-c", "pass"],
            "cwd": ".",
            "source": source,
            "artifacts": artifacts or ["oracle.txt"],
        }
        if oracle is None:
            if verification_type == "DIFFERENTIAL":
                oracle = {
                    "kind": "differential",
                    "expected_exit_code": 0,
                    "baseline": "baseline.txt",
                    "comparison": "bytes",
                }
            elif verification_type == "PERFORMANCE":
                oracle = {
                    "kind": "performance",
                    "expected_exit_code": 0,
                    "metric_pointer": "/value",
                    "runs_pointer": "/runs",
                    "operator": "lt",
                    "threshold": 100,
                    "minimum_runs": 2,
                    "method": "test benchmark",
                    "unit": "ms",
                }
            else:
                oracle = {"kind": "exit_code", "expected": 0}
        value["oracle"] = oracle
    elif verification_type == "STATIC":
        value["record"] = {"source_path": "README.md", "line": "1"}
    return value


def requirement(
    requirement_id: str = "R1",
    *,
    priority: str = "MUST",
    obligations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "text": f"Requirement {requirement_id}",
        "source_text": f"Original goal for {requirement_id}",
        "priority": priority,
        "notes": "",
        "obligations": obligations if obligations is not None else [obligation(f"{requirement_id}-O1")],
    }


def profile() -> dict[str, list[Any]]:
    return {
        "build_commands": [],
        "test_commands": [],
        "run_commands": [],
        "benchmark_commands": [],
        "relevant_paths": [],
        "discovered_from": [],
        "notes": [],
    }


def initialize_root(
    root: Path, requirements: list[dict[str, Any]], *, sealed: bool = True
) -> dict[str, Any]:
    for item in requirements:
        for item_obligation in item["obligations"]:
            for relative in item_obligation.get("experiment", {}).get("artifacts", []):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_text("sealed oracle artifact\n", encoding="utf-8")
            oracle = item_obligation.get("oracle", {})
            if oracle.get("kind") == "differential":
                path = root / oracle["baseline"]
                if not path.exists():
                    path.write_bytes(b"baseline\n")
            record = item_obligation.get("record")
            if record:
                path = root / record["source_path"]
                if not path.exists():
                    path.write_text("static evidence\n", encoding="utf-8")
    git_state = capture_git_state(root)
    snapshot = capture_file_snapshot(root)
    directory = create_layout(root)
    plan = {
        "version": "1",
        "goal": "Test goal",
        "created_at": utc_now(),
        "repository": {
            "root": str(root.resolve()),
            "git_commit": git_state["commit"],
            "worktree_dirty": git_state["dirty"],
        },
        "requirements": requirements,
    }
    write_json(directory / "plan.json", plan)
    write_json(
        directory / "session.json",
        {
            "version": "0",
            "initialized_at": utc_now(),
            "repository_before": git_state,
            "files_before": snapshot,
        },
    )
    repo_profile = profile()
    write_json(directory / "repo_profile.json", repo_profile)
    if sealed:
        seal_verification(root, plan, repo_profile)
    return plan
