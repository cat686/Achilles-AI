"""Sealed command execution and evidence capture for artifact schema v1."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .digest import sha256_bytes, sha256_file, sha256_json
from .evidence import create_layout, next_evidence_id, save_evidence, verification_path, write_json
from .git_state import capture_file_snapshot, capture_git_state, capture_paths_snapshot, compare_snapshots
from .monitoring import FilesystemMonitor
from .oracle import evaluate_oracle
from .schema_v1 import (
    CURRENT_VERSION,
    EXECUTABLE_TYPES,
    SchemaError,
    find_obligation,
    validate_assessment,
    validate_plan,
    validate_profile,
)
from .sealing import seal_sha256, validate_seal_state


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def environment_summary() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "os": os.name,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "machine": platform.machine(),
    }


def display_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)


def _relative_artifact(root: Path, path: Path) -> str:
    return path.relative_to(verification_path(root)).as_posix()


def _sealed_artifacts(obligation: dict[str, Any], seal: dict[str, Any]) -> dict[str, str]:
    paths = set(obligation.get("experiment", {}).get("artifacts", []))
    oracle = obligation.get("oracle", {})
    if oracle.get("kind") == "differential":
        paths.add(oracle["baseline"])
    if "record" in obligation:
        paths.add(obligation["record"]["source_path"])
    return {path: seal["artifact_sha256"][path] for path in sorted(paths)}


def _ensure_sealed(
    root: Path, plan: dict[str, Any], profile: dict[str, Any], seal: dict[str, Any]
) -> str:
    validate_plan(plan)
    validate_profile(profile)
    issues = validate_seal_state(root, plan, profile, seal)
    if issues:
        raise SchemaError("sealed verification is stale: " + "; ".join(issues))
    return seal_sha256(root)


def capture_command(
    *,
    root: Path,
    plan: dict[str, Any],
    profile: dict[str, Any],
    seal: dict[str, Any],
    requirement_id: str,
    obligation_id: str,
) -> dict[str, Any]:
    root = root.resolve()
    current_seal_sha256 = _ensure_sealed(root, plan, profile, seal)
    obligation = find_obligation(plan, requirement_id, obligation_id)
    verification_type = obligation["type"]
    if verification_type not in EXECUTABLE_TYPES:
        raise SchemaError(f"{verification_type} evidence must be recorded with 'verify record'")
    experiment = obligation["experiment"]
    command = list(experiment["argv"])
    cwd = (root / experiment["cwd"]).resolve()
    if not cwd.is_relative_to(root):
        raise SchemaError("sealed command cwd must remain inside the repository root")
    if not cwd.is_dir():
        raise SchemaError(f"sealed command cwd does not exist: {cwd}")

    create_layout(root)
    evidence_id = next_evidence_id(root)
    evidence_directory = verification_path(root) / "evidence"
    stdout_path = evidence_directory / f"{evidence_id}.stdout.bin"
    stderr_path = evidence_directory / f"{evidence_id}.stderr.bin"
    fs_events_path = evidence_directory / f"{evidence_id}.fs-events.json"
    started_at = utc_now()
    started_clock = time.perf_counter()
    git_before = capture_git_state(root)
    snapshot_before = capture_file_snapshot(root)
    protected_before = capture_paths_snapshot(root, seal["protected_paths"])
    stdout = b""
    stderr = b""
    exit_code: int | None = None
    status = "MONITOR_ERROR"
    process: subprocess.Popen[bytes] | None = None
    child_environment = os.environ.copy()
    child_environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    monitor = FilesystemMonitor(root, set(seal["protected_paths"]))
    monitor_started = False
    try:
        monitor.start()
        monitor_started = True
    except Exception as exc:
        stderr = f"Filesystem monitor failed: {type(exc).__name__}: {exc}\n".encode("utf-8", errors="replace")
    if monitor_started:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env=child_environment,
            )
            status = "EXECUTED"
            try:
                stdout, stderr = process.communicate()
                exit_code = process.returncode
            except KeyboardInterrupt:
                status = "INTERRUPTED"
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                exit_code = process.returncode
        except OSError as exc:
            status = "EXECUTION_ERROR"
            stderr = f"{type(exc).__name__}: {exc}\n".encode("utf-8", errors="replace")
        finally:
            monitor.stop()
    finished_at = utc_now()
    duration_seconds = round(time.perf_counter() - started_clock, 6)
    monitor_result = monitor.result()
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    write_json(fs_events_path, monitor_result)

    git_after = capture_git_state(root)
    snapshot_after = capture_file_snapshot(root)
    protected_after = capture_paths_snapshot(root, seal["protected_paths"])
    repository_changes = compare_snapshots(snapshot_before, snapshot_after)
    protected_changes = compare_snapshots(protected_before, protected_after)
    persistent_protected_change = sha256_json(protected_before) != sha256_json(protected_after)
    integrity_valid = not (
        monitor_result["error"]
        or monitor_result["overflow"]
        or monitor_result["protected_events"]
        or persistent_protected_change
        or protected_before["errors"]
        or protected_after["errors"]
    )

    assessment = "INCONCLUSIVE"
    oracle_result: dict[str, Any] = {"evaluated": False}
    if not integrity_valid:
        assessment_reason = "Command evidence is inconclusive because protected repository integrity was not preserved."
    elif status != "EXECUTED" or exit_code is None:
        assessment_reason = f"Command status was {status}; inability to execute is not a counterexample."
    else:
        assessment, assessment_reason, oracle_result = evaluate_oracle(
            root=root, oracle=obligation["oracle"], exit_code=exit_code, stdout=stdout
        )
        oracle_result["evaluated"] = True

    value: dict[str, Any] = {
        "version": CURRENT_VERSION,
        "id": evidence_id,
        "session_id": seal["session_id"],
        "seal_sha256": current_seal_sha256,
        "requirement_id": requirement_id,
        "obligation_id": obligation_id,
        "type": verification_type,
        "source": experiment["source"],
        "command": display_command(command),
        "command_args": command,
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "exit_code": exit_code,
        "stdout_path": _relative_artifact(root, stdout_path),
        "stderr_path": _relative_artifact(root, stderr_path),
        "fs_events_path": _relative_artifact(root, fs_events_path),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "fs_events_sha256": sha256_file(fs_events_path),
        "git_commit": git_before["commit"],
        "git_dirty": git_before["dirty"],
        "git_state_before": git_before,
        "git_state_after": git_after,
        "environment": environment_summary(),
        "status": status,
        "assessment": assessment,
        "assessment_reason": assessment_reason,
        "oracle": obligation["oracle"],
        "oracle_result": oracle_result,
        "artifact_sha256": _sealed_artifacts(obligation, seal),
        "snapshot_before_sha256": sha256_json(snapshot_before),
        "snapshot_after_sha256": sha256_json(snapshot_after),
        "protected_snapshot_before_sha256": sha256_json(protected_before),
        "protected_snapshot_after_sha256": sha256_json(protected_after),
        "repository_changes": repository_changes,
        "integrity": {
            "valid": integrity_valid,
            "protected_changes": protected_changes,
            "protected_events": monitor_result["protected_events"],
            "event_count": monitor_result["event_count"],
            "event_overflow": monitor_result["overflow"],
            "monitor_error": monitor_result["error"],
        },
        "obligation_description": obligation["description"],
    }
    save_evidence(root, value)
    return value


def record_static_evidence(
    *,
    root: Path,
    plan: dict[str, Any],
    profile: dict[str, Any],
    seal: dict[str, Any],
    requirement_id: str,
    obligation_id: str,
    description: str | None,
    assessment: str,
) -> dict[str, Any]:
    root = root.resolve()
    current_seal_sha256 = _ensure_sealed(root, plan, profile, seal)
    obligation = find_obligation(plan, requirement_id, obligation_id)
    verification_type = obligation["type"]
    if verification_type not in {"STATIC", "HUMAN", "UNKNOWN"}:
        raise SchemaError(f"{verification_type} evidence must be captured with 'verify run'")
    validate_assessment(assessment)
    if verification_type in {"HUMAN", "UNKNOWN"} and assessment == "SUPPORTS":
        raise SchemaError(f"{verification_type} evidence cannot support an automatic PASS")
    source_path: str | None = None
    line: str | None = None
    digest: str | None = None
    if verification_type == "STATIC":
        source_path = obligation["record"]["source_path"]
        line = obligation["record"].get("line")
        source = (root / source_path).resolve()
        digest = sha256_file(source)
    now = utc_now()
    git_state = capture_git_state(root)
    value = {
        "version": CURRENT_VERSION,
        "id": next_evidence_id(root),
        "session_id": seal["session_id"],
        "seal_sha256": current_seal_sha256,
        "requirement_id": requirement_id,
        "obligation_id": obligation_id,
        "type": verification_type,
        "source": source_path or "manual_observation",
        "source_path": source_path,
        "source_sha256": digest,
        "line": line,
        "description": description or obligation["description"],
        "command": None,
        "cwd": str(root),
        "started_at": now,
        "finished_at": now,
        "duration_seconds": 0.0,
        "exit_code": None,
        "stdout_path": None,
        "stderr_path": None,
        "git_commit": git_state["commit"],
        "git_dirty": git_state["dirty"],
        "git_state_before": git_state,
        "git_state_after": git_state,
        "environment": environment_summary(),
        "status": "RECORDED",
        "assessment": assessment,
        "assessment_reason": description or obligation["description"],
        "artifact_sha256": _sealed_artifacts(obligation, seal),
        "obligation_description": obligation["description"],
    }
    save_evidence(root, value)
    return value
