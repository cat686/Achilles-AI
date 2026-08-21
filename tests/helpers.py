from __future__ import annotations

from pathlib import Path
from typing import Any

from goal_verifier.capture import utc_now
from goal_verifier.evidence import create_layout, write_json
from goal_verifier.git_state import capture_file_snapshot, capture_git_state


def obligation(
    obligation_id: str = "R1-O1", verification_type: str = "TEST", mandatory: bool = True
) -> dict[str, Any]:
    return {
        "id": obligation_id,
        "type": verification_type,
        "mandatory": mandatory,
        "description": f"Verify {obligation_id}",
        "planned_experiment": "Run a requirement-derived experiment",
    }


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


def initialize_root(root: Path, requirements: list[dict[str, Any]]) -> dict[str, Any]:
    git_state = capture_git_state(root)
    snapshot = capture_file_snapshot(root)
    directory = create_layout(root)
    plan = {
        "version": "0",
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
    write_json(
        directory / "repo_profile.json",
        {
            "build_commands": [],
            "test_commands": [],
            "run_commands": [],
            "benchmark_commands": [],
            "relevant_paths": [],
            "discovered_from": [],
            "notes": [],
        },
    )
    return plan

