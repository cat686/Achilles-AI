"""Deterministic command and static-evidence capture."""

from __future__ import annotations

import hashlib
import os
import platform
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .evidence import create_layout, next_evidence_id, save_evidence, verification_path
from .git_state import capture_git_state
from .schema import EXECUTABLE_TYPES, SchemaError, find_obligation, validate_plan, validate_verification_type


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


def _check_target(
    plan: dict[str, Any], requirement_id: str, obligation_id: str, verification_type: str
) -> dict[str, Any]:
    validate_plan(plan)
    verification_type = validate_verification_type(verification_type)
    obligation = find_obligation(plan, requirement_id, obligation_id)
    if obligation["type"] != verification_type:
        raise SchemaError(
            f"type mismatch for {obligation_id}: plan has {obligation['type']}, command requested {verification_type}"
        )
    return obligation


def _relative_artifact(root: Path, path: Path) -> str:
    return path.relative_to(verification_path(root)).as_posix()


def _valid_performance_measurement(measurement: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(measurement, dict)
        and measurement.get("threshold") is not None
        and measurement.get("observed_value") is not None
        and isinstance(measurement.get("measurement_method"), str)
        and measurement["measurement_method"].strip()
        and "number_of_runs" in measurement
    )


def capture_command(
    *,
    root: Path,
    plan: dict[str, Any],
    requirement_id: str,
    obligation_id: str,
    verification_type: str,
    command: Sequence[str],
    cwd: Path | None = None,
    source: str = "command",
    expected_exit_code: int | None = None,
    baseline: str | None = None,
    measurement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obligation = _check_target(plan, requirement_id, obligation_id, verification_type)
    if verification_type not in EXECUTABLE_TYPES:
        raise SchemaError(f"{verification_type} evidence must be recorded with 'verify record', not 'verify run'")
    if not command:
        raise SchemaError("a command is required after '--'")
    root = root.resolve()
    cwd = (cwd or root).resolve()
    if not cwd.is_relative_to(root):
        raise SchemaError("command cwd must remain inside the repository root")
    if not cwd.is_dir():
        raise SchemaError(f"command cwd does not exist: {cwd}")
    create_layout(root)
    evidence_id = next_evidence_id(root)
    evidence_directory = verification_path(root) / "evidence"
    stdout_path = evidence_directory / f"{evidence_id}.stdout.txt"
    stderr_path = evidence_directory / f"{evidence_id}.stderr.txt"
    started_at = utc_now()
    started_clock = time.perf_counter()
    git_before = capture_git_state(root)
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    status = "EXECUTED"
    process: subprocess.Popen[str] | None = None
    child_environment = os.environ.copy()
    child_environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=child_environment,
        )
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
        stderr = f"{type(exc).__name__}: {exc}\n"
    finished_at = utc_now()
    duration_seconds = round(time.perf_counter() - started_clock, 6)
    stdout_path.write_text(stdout, encoding="utf-8", newline="\n")
    stderr_path.write_text(stderr, encoding="utf-8", newline="\n")
    git_after = capture_git_state(root)

    assessment = "INCONCLUSIVE"
    assessment_reason = "No explicit executable oracle was supplied; exit code alone is not requirement proof."
    if status == "EXECUTED" and expected_exit_code is not None:
        if verification_type == "DIFFERENTIAL" and not baseline:
            assessment_reason = "No explicit trustworthy baseline was recorded for differential evidence."
        elif verification_type == "PERFORMANCE" and not _valid_performance_measurement(measurement):
            assessment_reason = "Performance evidence lacks threshold, observation, method, or run-count metadata."
        elif exit_code == expected_exit_code:
            assessment = "SUPPORTS"
            assessment_reason = f"The requirement-derived command met the explicit exit-code oracle ({expected_exit_code})."
        else:
            assessment = "CONTRADICTS"
            assessment_reason = f"Expected exit code {expected_exit_code}, observed {exit_code}."
    elif status != "EXECUTED":
        assessment_reason = f"Command status was {status}; inability to execute is not a counterexample."

    value: dict[str, Any] = {
        "id": evidence_id,
        "requirement_id": requirement_id,
        "obligation_id": obligation_id,
        "type": verification_type,
        "source": source,
        "command": display_command(command),
        "command_args": list(command),
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "exit_code": exit_code,
        "stdout_path": _relative_artifact(root, stdout_path),
        "stderr_path": _relative_artifact(root, stderr_path),
        "git_commit": git_before["commit"],
        "git_dirty": git_before["dirty"],
        "git_state_before": git_before,
        "git_state_after": git_after,
        "environment": environment_summary(),
        "status": status,
        "assessment": assessment,
        "assessment_reason": assessment_reason,
        "oracle": {"expected_exit_code": expected_exit_code} if expected_exit_code is not None else None,
        "baseline": baseline,
        "measurement": measurement,
        "obligation_description": obligation["description"],
    }
    save_evidence(root, value)
    return value


def record_static_evidence(
    *,
    root: Path,
    plan: dict[str, Any],
    requirement_id: str,
    obligation_id: str,
    verification_type: str,
    source_path: str | None,
    description: str,
    assessment: str,
    line: str | None = None,
) -> dict[str, Any]:
    obligation = _check_target(plan, requirement_id, obligation_id, verification_type)
    if verification_type not in {"STATIC", "HUMAN", "UNKNOWN"}:
        raise SchemaError(f"{verification_type} evidence must be captured with 'verify run'")
    if assessment not in {"SUPPORTS", "CONTRADICTS", "INCONCLUSIVE"}:
        raise SchemaError(f"invalid assessment: {assessment}")
    if verification_type in {"HUMAN", "UNKNOWN"} and assessment == "SUPPORTS":
        raise SchemaError(f"{verification_type} evidence cannot support an automatic PASS")
    root = root.resolve()
    create_layout(root)
    resolved_source: Path | None = None
    digest: str | None = None
    stored_source = source_path
    if source_path:
        candidate = Path(source_path)
        resolved_source = (candidate if candidate.is_absolute() else root / candidate).resolve()
        if not resolved_source.is_relative_to(root):
            raise SchemaError("static evidence source must remain inside the repository root")
        if not resolved_source.is_file():
            raise SchemaError(f"static evidence source is not a file: {resolved_source}")
        stored_source = resolved_source.relative_to(root).as_posix()
        digest = hashlib.sha256(resolved_source.read_bytes()).hexdigest()
    elif verification_type == "STATIC":
        raise SchemaError("STATIC evidence requires --source")

    evidence_id = next_evidence_id(root)
    now = utc_now()
    git_state = capture_git_state(root)
    value = {
        "id": evidence_id,
        "requirement_id": requirement_id,
        "obligation_id": obligation_id,
        "type": verification_type,
        "source": stored_source or "manual_observation",
        "source_path": stored_source,
        "source_sha256": digest,
        "line": line,
        "description": description,
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
        "assessment_reason": description,
        "obligation_description": obligation["description"],
    }
    save_evidence(root, value)
    return value


# Public imports now resolve to the sealed artifact-schema-v1 implementation.
from .capture_v1 import *  # noqa: E402,F401,F403
