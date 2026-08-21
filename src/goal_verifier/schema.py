"""Small, dependency-free validators for Version 0 artifacts."""

from __future__ import annotations

import re
from typing import Any


VERIFICATION_TYPES = frozenset(
    {"STATIC", "BUILD", "TEST", "RUNTIME", "DIFFERENTIAL", "PERFORMANCE", "HUMAN", "UNKNOWN"}
)
VERDICTS = frozenset({"PASS", "FAIL", "PARTIAL", "UNKNOWN"})
PRIORITIES = frozenset({"MUST", "SHOULD", "MAY"})
ASSESSMENTS = frozenset({"SUPPORTS", "CONTRADICTS", "INCONCLUSIVE"})
EXECUTABLE_TYPES = frozenset({"BUILD", "TEST", "RUNTIME", "DIFFERENTIAL", "PERFORMANCE"})


class SchemaError(ValueError):
    """Raised when a persisted artifact violates the Version 0 schema."""


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{label} must be a JSON object")
    return value


def _string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise SchemaError(f"{label} must be a non-empty string")
    return value


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


def validate_requirements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise SchemaError("requirements must be a JSON array")
    requirement_ids: set[str] = set()
    obligation_ids: set[str] = set()
    for index, item in enumerate(value):
        requirement = _mapping(item, f"requirements[{index}]")
        requirement_id = _string(requirement.get("id"), f"requirements[{index}].id")
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
            obligation = _mapping(raw_obligation, f"{requirement_id}.obligations[{obligation_index}]")
            obligation_id = _string(obligation.get("id"), f"{requirement_id}.obligation.id")
            if obligation_id in obligation_ids:
                raise SchemaError(f"duplicate obligation id: {obligation_id}")
            obligation_ids.add(obligation_id)
            validate_verification_type(obligation.get("type"))
            if not isinstance(obligation.get("mandatory"), bool):
                raise SchemaError(f"{obligation_id}.mandatory must be boolean")
            _string(obligation.get("description"), f"{obligation_id}.description")
            _string(obligation.get("planned_experiment"), f"{obligation_id}.planned_experiment")
    return value


def validate_plan(value: Any) -> dict[str, Any]:
    plan = _mapping(value, "plan")
    if plan.get("version") != "0":
        raise SchemaError("plan.version must be '0'")
    _string(plan.get("goal"), "plan.goal")
    _string(plan.get("created_at"), "plan.created_at")
    repository = _mapping(plan.get("repository"), "plan.repository")
    _string(repository.get("root"), "plan.repository.root")
    if repository.get("git_commit") is not None and not isinstance(repository.get("git_commit"), str):
        raise SchemaError("plan.repository.git_commit must be a string or null")
    if repository.get("worktree_dirty") is not None and not isinstance(repository.get("worktree_dirty"), bool):
        raise SchemaError("plan.repository.worktree_dirty must be boolean or null")
    validate_requirements(plan.get("requirements"))
    return plan


def validate_evidence(value: Any) -> dict[str, Any]:
    evidence = _mapping(value, "evidence")
    evidence_id = _string(evidence.get("id"), "evidence.id")
    if not re.fullmatch(r"E\d{4,}", evidence_id):
        raise SchemaError(f"invalid evidence id: {evidence_id}")
    _string(evidence.get("requirement_id"), "evidence.requirement_id")
    _string(evidence.get("obligation_id"), "evidence.obligation_id")
    evidence_type = validate_verification_type(evidence.get("type"))
    assessment = validate_assessment(evidence.get("assessment"))
    if evidence_type in {"HUMAN", "UNKNOWN"} and assessment == "SUPPORTS":
        raise SchemaError(f"{evidence_type} evidence cannot support an automatic PASS")
    _string(evidence.get("source"), "evidence.source")
    _string(evidence.get("status"), "evidence.status")
    if evidence.get("git_commit") is not None and not isinstance(evidence.get("git_commit"), str):
        raise SchemaError("evidence.git_commit must be a string or null")
    if evidence.get("git_dirty") is not None and not isinstance(evidence.get("git_dirty"), bool):
        raise SchemaError("evidence.git_dirty must be boolean or null")
    if "environment" not in evidence or not isinstance(evidence["environment"], dict):
        raise SchemaError("evidence.environment must be an object")
    if evidence.get("command") is not None:
        _string(evidence.get("command"), "evidence.command")
        if not isinstance(evidence.get("command_args"), list) or not all(
            isinstance(part, str) for part in evidence["command_args"]
        ):
            raise SchemaError("evidence.command_args must be an array of strings")
        for field in ("started_at", "finished_at", "stdout_path", "stderr_path"):
            _string(evidence.get(field), f"evidence.{field}")
        if not isinstance(evidence.get("duration_seconds"), (int, float)) or evidence["duration_seconds"] < 0:
            raise SchemaError("evidence.duration_seconds must be non-negative")
        if evidence.get("exit_code") is not None and not isinstance(evidence.get("exit_code"), int):
            raise SchemaError("evidence.exit_code must be an integer or null")
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


# Artifact schema v1 supersedes the Version 0 definitions above. Keeping this
# compatibility module avoids changing public imports while legacy artifacts
# remain readable by the v1 implementation.
from .schema_v1 import *  # noqa: E402,F401,F403
