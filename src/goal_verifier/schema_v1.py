"""Strict validators for Achilles-AI artifact schema v1."""

from __future__ import annotations

import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


CURRENT_VERSION = "1"
LEGACY_VERSION = "0"
VERIFICATION_TYPES = frozenset(
    {"STATIC", "BUILD", "TEST", "RUNTIME", "DIFFERENTIAL", "PERFORMANCE", "HUMAN", "UNKNOWN"}
)
VERDICTS = frozenset({"PASS", "FAIL", "PARTIAL", "UNKNOWN"})
PRIORITIES = frozenset({"MUST", "SHOULD", "MAY"})
ASSESSMENTS = frozenset({"SUPPORTS", "CONTRADICTS", "INCONCLUSIVE"})
EXECUTABLE_TYPES = frozenset({"BUILD", "TEST", "RUNTIME", "DIFFERENTIAL", "PERFORMANCE"})
COMMAND_ORACLE_TYPES = frozenset({"BUILD", "TEST", "RUNTIME"})
EXPERIMENT_SOURCES = frozenset({"existing_test", "generated_test", "project_command"})
PERFORMANCE_OPERATORS = frozenset({"lt", "lte", "gt", "gte", "eq"})


class SchemaError(ValueError):
    """Raised when a persisted artifact violates its schema."""


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{label} must be a JSON object")
    return value


def _strict_keys(
    value: dict[str, Any], label: str, *, required: set[str], optional: set[str] | None = None
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise SchemaError(f"{label} is missing fields: {', '.join(missing)}")
    if unknown:
        raise SchemaError(f"{label} has unknown fields: {', '.join(unknown)}")


def _string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SchemaError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(f"{label} must be an integer")
    return value


def _finite_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SchemaError(f"{label} must be a finite number")
    return value


def _relative_path(value: Any, label: str) -> str:
    text = _string(value, label)
    path = Path(text)
    if (
        path.is_absolute()
        or path.drive
        or PurePosixPath(text).is_absolute()
        or PureWindowsPath(text).is_absolute()
        or ".." in PurePosixPath(text).parts
        or ".." in PureWindowsPath(text).parts
    ):
        raise SchemaError(f"{label} must be a repository-relative path without '..'")
    return text


def validate_verification_type(value: Any) -> str:
    value = _string(value, "verification type")
    if value not in VERIFICATION_TYPES:
        raise SchemaError(f"invalid verification type: {value}")
    return value


def validate_verdict(value: Any) -> str:
    value = _string(value, "verdict")
    if value not in VERDICTS:
        raise SchemaError(f"invalid verdict: {value}")
    return value


def validate_assessment(value: Any) -> str:
    value = _string(value, "assessment")
    if value not in ASSESSMENTS:
        raise SchemaError(f"invalid evidence assessment: {value}")
    return value


def _validate_experiment(value: Any, label: str) -> dict[str, Any]:
    experiment = _mapping(value, label)
    _strict_keys(experiment, label, required={"argv", "cwd", "source", "artifacts"})
    argv = experiment["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
        raise SchemaError(f"{label}.argv must be a non-empty array of non-empty strings")
    _relative_path(experiment["cwd"], f"{label}.cwd")
    source = _string(experiment["source"], f"{label}.source")
    if source not in EXPERIMENT_SOURCES:
        raise SchemaError(f"invalid experiment source for {label}: {source}")
    artifacts = experiment["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise SchemaError(f"{label}.artifacts must be a non-empty array")
    normalized = [_relative_path(item, f"{label}.artifacts") for item in artifacts]
    if len(normalized) != len(set(normalized)):
        raise SchemaError(f"{label}.artifacts must not contain duplicates")
    if source == "generated_test" and not any(
        Path(item).as_posix().startswith(".verification/generated/") for item in normalized
    ):
        raise SchemaError(f"{label} generated_test must declare an artifact under .verification/generated/")
    return experiment


def _validate_oracle(value: Any, verification_type: str, label: str) -> dict[str, Any]:
    oracle = _mapping(value, label)
    kind = _string(oracle.get("kind"), f"{label}.kind")
    if kind == "exit_code":
        _strict_keys(oracle, label, required={"kind", "expected"})
        _integer(oracle["expected"], f"{label}.expected")
        if verification_type not in COMMAND_ORACLE_TYPES:
            raise SchemaError(f"{kind} oracle is not valid for {verification_type}")
    elif kind == "stdout_json":
        _strict_keys(oracle, label, required={"kind", "expected_exit_code"})
        _integer(oracle["expected_exit_code"], f"{label}.expected_exit_code")
        if verification_type not in COMMAND_ORACLE_TYPES:
            raise SchemaError(f"{kind} oracle is not valid for {verification_type}")
    elif kind == "differential":
        _strict_keys(oracle, label, required={"kind", "expected_exit_code", "baseline", "comparison"})
        _integer(oracle["expected_exit_code"], f"{label}.expected_exit_code")
        _relative_path(oracle["baseline"], f"{label}.baseline")
        comparison = _string(oracle["comparison"], f"{label}.comparison")
        if comparison not in {"bytes", "json"}:
            raise SchemaError(f"{label}.comparison must be 'bytes' or 'json'")
        if verification_type != "DIFFERENTIAL":
            raise SchemaError("differential oracle requires a DIFFERENTIAL obligation")
    elif kind == "performance":
        _strict_keys(
            oracle,
            label,
            required={
                "kind",
                "expected_exit_code",
                "metric_pointer",
                "runs_pointer",
                "operator",
                "threshold",
                "minimum_runs",
                "method",
                "unit",
            },
        )
        _integer(oracle["expected_exit_code"], f"{label}.expected_exit_code")
        for field in ("metric_pointer", "runs_pointer"):
            pointer = _string(oracle[field], f"{label}.{field}")
            if not pointer.startswith("/"):
                raise SchemaError(f"{label}.{field} must be an RFC 6901 JSON pointer")
        operator = _string(oracle["operator"], f"{label}.operator")
        if operator not in PERFORMANCE_OPERATORS:
            raise SchemaError(f"invalid performance operator: {operator}")
        _finite_number(oracle["threshold"], f"{label}.threshold")
        if _integer(oracle["minimum_runs"], f"{label}.minimum_runs") < 1:
            raise SchemaError(f"{label}.minimum_runs must be positive")
        _string(oracle["method"], f"{label}.method")
        _string(oracle["unit"], f"{label}.unit")
        if verification_type != "PERFORMANCE":
            raise SchemaError("performance oracle requires a PERFORMANCE obligation")
    else:
        raise SchemaError(f"invalid oracle kind: {kind}")
    return oracle


def validate_requirements(value: Any, *, version: str = CURRENT_VERSION) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SchemaError("requirements must be a JSON array")
    requirement_ids: set[str] = set()
    obligation_ids: set[str] = set()
    for index, item in enumerate(value):
        label = f"requirements[{index}]"
        requirement = _mapping(item, label)
        if version == CURRENT_VERSION:
            _strict_keys(
                requirement,
                label,
                required={"id", "text", "source_text", "priority", "obligations"},
                optional={"notes"},
            )
        requirement_id = _string(requirement.get("id"), f"{label}.id")
        if not re.fullmatch(r"R[0-9A-Za-z_-]+", requirement_id):
            raise SchemaError(f"invalid requirement id: {requirement_id}")
        if requirement_id in requirement_ids:
            raise SchemaError(f"duplicate requirement id: {requirement_id}")
        requirement_ids.add(requirement_id)
        _string(requirement.get("text"), f"{requirement_id}.text")
        _string(requirement.get("source_text"), f"{requirement_id}.source_text")
        priority = _string(requirement.get("priority"), f"{requirement_id}.priority")
        if priority not in PRIORITIES:
            raise SchemaError(f"invalid priority for {requirement_id}: {priority}")
        if "notes" in requirement and not isinstance(requirement["notes"], str):
            raise SchemaError(f"{requirement_id}.notes must be a string")
        obligations = requirement.get("obligations")
        if not isinstance(obligations, list):
            raise SchemaError(f"{requirement_id}.obligations must be a JSON array")
        for obligation_index, raw_obligation in enumerate(obligations):
            obligation_label = f"{requirement_id}.obligations[{obligation_index}]"
            obligation = _mapping(raw_obligation, obligation_label)
            if version == CURRENT_VERSION:
                _strict_keys(
                    obligation,
                    obligation_label,
                    required={"id", "type", "mandatory", "description", "planned_experiment"},
                    optional={"experiment", "oracle", "record"},
                )
            obligation_id = _string(obligation.get("id"), f"{obligation_label}.id")
            if not obligation_id.startswith(f"{requirement_id}-O"):
                raise SchemaError(f"obligation {obligation_id} must belong to {requirement_id}")
            if obligation_id in obligation_ids:
                raise SchemaError(f"duplicate obligation id: {obligation_id}")
            obligation_ids.add(obligation_id)
            verification_type = validate_verification_type(obligation.get("type"))
            if not isinstance(obligation.get("mandatory"), bool):
                raise SchemaError(f"{obligation_id}.mandatory must be boolean")
            _string(obligation.get("description"), f"{obligation_id}.description")
            _string(obligation.get("planned_experiment"), f"{obligation_id}.planned_experiment")
            if version != CURRENT_VERSION:
                continue
            if verification_type in EXECUTABLE_TYPES:
                _validate_experiment(obligation.get("experiment"), f"{obligation_id}.experiment")
                _validate_oracle(obligation.get("oracle"), verification_type, f"{obligation_id}.oracle")
                if "record" in obligation:
                    raise SchemaError(f"{obligation_id}.record is not valid for executable evidence")
            elif verification_type == "STATIC":
                record = _mapping(obligation.get("record"), f"{obligation_id}.record")
                _strict_keys(record, f"{obligation_id}.record", required={"source_path"}, optional={"line"})
                _relative_path(record["source_path"], f"{obligation_id}.record.source_path")
                if "line" in record:
                    _string(record["line"], f"{obligation_id}.record.line")
                if "experiment" in obligation or "oracle" in obligation:
                    raise SchemaError(f"{obligation_id} STATIC evidence cannot define experiment/oracle")
            elif any(field in obligation for field in ("experiment", "oracle", "record")):
                raise SchemaError(f"{obligation_id} HUMAN/UNKNOWN evidence cannot define automatic verification")
    return value


def validate_plan(value: Any, *, allow_legacy: bool = False) -> dict[str, Any]:
    plan = _mapping(value, "plan")
    version = plan.get("version")
    if version == LEGACY_VERSION and allow_legacy:
        validate_requirements(plan.get("requirements"), version=LEGACY_VERSION)
        return plan
    if version != CURRENT_VERSION:
        if version == LEGACY_VERSION:
            raise SchemaError("artifact schema v0 is legacy; reinitialize and seal a v1 verification")
        raise SchemaError(f"plan.version must be '{CURRENT_VERSION}'")
    _strict_keys(plan, "plan", required={"version", "goal", "created_at", "repository", "requirements"})
    _string(plan.get("goal"), "plan.goal")
    _string(plan.get("created_at"), "plan.created_at")
    repository = _mapping(plan.get("repository"), "plan.repository")
    _strict_keys(repository, "plan.repository", required={"root", "git_commit", "worktree_dirty"})
    _string(repository.get("root"), "plan.repository.root")
    if repository.get("git_commit") is not None and not isinstance(repository.get("git_commit"), str):
        raise SchemaError("plan.repository.git_commit must be a string or null")
    if repository.get("worktree_dirty") is not None and not isinstance(repository.get("worktree_dirty"), bool):
        raise SchemaError("plan.repository.worktree_dirty must be boolean or null")
    validate_requirements(plan.get("requirements"))
    return plan


def validate_profile(value: Any) -> dict[str, Any]:
    profile = _mapping(value, "repo profile")
    required = {
        "build_commands",
        "test_commands",
        "run_commands",
        "benchmark_commands",
        "relevant_paths",
        "discovered_from",
        "notes",
    }
    _strict_keys(profile, "repo profile", required=required)
    for field in required:
        if not isinstance(profile[field], list):
            raise SchemaError(f"repo profile.{field} must be a JSON array")
    for field in ("relevant_paths", "discovered_from", "notes"):
        if not all(isinstance(item, str) for item in profile[field]):
            raise SchemaError(f"repo profile.{field} must contain strings")
    return profile


def validate_evidence(value: Any, *, allow_legacy: bool = False) -> dict[str, Any]:
    evidence = _mapping(value, "evidence")
    version = evidence.get("version", LEGACY_VERSION)
    if version == LEGACY_VERSION and allow_legacy:
        validate_assessment(evidence.get("assessment"))
        return evidence
    if version != CURRENT_VERSION:
        raise SchemaError("evidence is not artifact schema v1")
    evidence_id = _string(evidence.get("id"), "evidence.id")
    if not re.fullmatch(r"E\d{4,}", evidence_id):
        raise SchemaError(f"invalid evidence id: {evidence_id}")
    for field in ("session_id", "seal_sha256", "requirement_id", "obligation_id", "source", "status"):
        _string(evidence.get(field), f"evidence.{field}")
    evidence_type = validate_verification_type(evidence.get("type"))
    assessment = validate_assessment(evidence.get("assessment"))
    if evidence_type in {"HUMAN", "UNKNOWN"} and assessment == "SUPPORTS":
        raise SchemaError(f"{evidence_type} evidence cannot support an automatic PASS")
    if not isinstance(evidence.get("environment"), dict):
        raise SchemaError("evidence.environment must be an object")
    if evidence.get("command") is not None:
        _string(evidence.get("command"), "evidence.command")
        if not isinstance(evidence.get("command_args"), list) or not all(
            isinstance(part, str) for part in evidence["command_args"]
        ):
            raise SchemaError("evidence.command_args must be an array of strings")
        for field in (
            "started_at",
            "finished_at",
            "stdout_path",
            "stderr_path",
            "fs_events_path",
            "stdout_sha256",
            "stderr_sha256",
            "fs_events_sha256",
        ):
            _string(evidence.get(field), f"evidence.{field}")
        if not isinstance(evidence.get("duration_seconds"), (int, float)) or evidence["duration_seconds"] < 0:
            raise SchemaError("evidence.duration_seconds must be non-negative")
        if evidence.get("exit_code") is not None:
            _integer(evidence.get("exit_code"), "evidence.exit_code")
        if not isinstance(evidence.get("integrity"), dict):
            raise SchemaError("evidence.integrity must be an object")
    return evidence


def find_obligation(plan: dict[str, Any], requirement_id: str, obligation_id: str) -> dict[str, Any]:
    for requirement in plan["requirements"]:
        if requirement["id"] != requirement_id:
            continue
        for obligation in requirement["obligations"]:
            if obligation["id"] == obligation_id:
                return obligation
        raise SchemaError(f"obligation {obligation_id} does not belong to requirement {requirement_id}")
    raise SchemaError(f"requirement not found in plan: {requirement_id}")
