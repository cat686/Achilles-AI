"""Plan sealing and protected repository-state validation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .digest import sha256_file, sha256_json
from .evidence import create_layout, read_json, verification_path, write_json
from .git_state import capture_file_snapshot, capture_git_state, capture_paths_snapshot, capture_tracked_paths
from .schema import CURRENT_VERSION, SchemaError, validate_plan, validate_profile


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _artifact_paths(plan: dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    for requirement in plan["requirements"]:
        for obligation in requirement["obligations"]:
            if "experiment" in obligation:
                paths.update(Path(item).as_posix() for item in obligation["experiment"]["artifacts"])
            oracle = obligation.get("oracle", {})
            if oracle.get("kind") == "differential":
                paths.add(Path(oracle["baseline"]).as_posix())
            if "record" in obligation:
                paths.add(Path(obligation["record"]["source_path"]).as_posix())
    return sorted(paths)


def _seal_summary(plan: dict[str, Any], seal: dict[str, Any], seal_sha256: str) -> str:
    lines = [
        "# Verification Seal",
        "",
        f"- Session: `{seal['session_id']}`",
        f"- Sealed at: `{seal['sealed_at']}`",
        f"- Repository: `{seal['repository_root']}`",
        f"- Seal SHA-256: `{seal_sha256}`",
        f"- Plan SHA-256: `{seal['plan_sha256']}`",
        f"- Profile SHA-256: `{seal['profile_sha256']}`",
        "",
        "## Experiments",
        "",
    ]
    for requirement in plan["requirements"]:
        for obligation in requirement["obligations"]:
            lines.append(f"### {obligation['id']} — {obligation['type']}")
            lines.append("")
            if "experiment" in obligation:
                experiment = obligation["experiment"]
                lines.append(f"- Command argv: `{experiment['argv']}`")
                lines.append(f"- CWD: `{experiment['cwd']}`")
                lines.append(f"- Source: `{experiment['source']}`")
                lines.append(f"- Oracle: `{obligation['oracle']}`")
                lines.append(f"- Artifacts: `{experiment['artifacts']}`")
            elif "record" in obligation:
                lines.append(f"- Static source: `{obligation['record']['source_path']}`")
            else:
                lines.append("- No automatic oracle is declared.")
            lines.append("")
    lines.extend(["## Artifact Digests", ""])
    if seal["artifact_sha256"]:
        lines.extend(f"- `{path}`: `{digest}`" for path, digest in seal["artifact_sha256"].items())
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def seal_verification(root: Path, plan: dict[str, Any], profile: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    root = root.resolve()
    validate_plan(plan)
    validate_profile(profile)
    if Path(plan["repository"]["root"]).resolve() != root:
        raise SchemaError("plan.repository.root does not match the active repository root")
    directory = create_layout(root)
    evidence_directory = directory / "evidence"
    if any(evidence_directory.iterdir()):
        raise SchemaError("cannot seal or reseal after evidence has been created")

    existing_path = directory / "seal.json"
    if existing_path.is_file():
        existing = read_json(existing_path)
        issues = validate_seal_state(root, plan, profile, existing)
        if issues:
            raise SchemaError("existing seal is stale: " + "; ".join(issues))
        return existing, False

    repository_snapshot = capture_file_snapshot(root)
    git_state = capture_git_state(root)
    tracked = capture_tracked_paths(root)
    protected_paths = set(tracked if tracked is not None else repository_snapshot["files"])
    artifacts = _artifact_paths(plan)
    artifact_sha256: dict[str, str] = {}
    for relative in artifacts:
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SchemaError(f"sealed artifact escapes repository root: {relative}") from exc
        if not path.is_file():
            raise SchemaError(f"sealed artifact is not a file: {relative}")
        artifact_sha256[relative] = sha256_file(path)
        protected_paths.add(relative)
    protected_snapshot = capture_paths_snapshot(root, protected_paths)
    if protected_snapshot["errors"]:
        raise SchemaError("unable to hash protected paths: " + "; ".join(protected_snapshot["errors"]))

    seal = {
        "version": CURRENT_VERSION,
        "session_id": uuid4().hex,
        "sealed_at": _utc_now(),
        "repository_root": str(root),
        "git_state": git_state,
        "plan_sha256": sha256_json(plan),
        "profile_sha256": sha256_json(profile),
        "artifact_sha256": artifact_sha256,
        "protected_paths": sorted(protected_paths),
        "protected_snapshot": protected_snapshot,
        "protected_snapshot_sha256": sha256_json(protected_snapshot),
        "repository_snapshot": repository_snapshot,
        "repository_snapshot_sha256": sha256_json(repository_snapshot),
    }
    write_json(existing_path, seal)
    seal_sha256 = sha256_file(existing_path)
    write_json(
        directory / "ledger.json",
        {"version": CURRENT_VERSION, "session_id": seal["session_id"], "seal_sha256": seal_sha256, "entries": []},
    )
    (directory / "seal-summary.md").write_text(
        _seal_summary(plan, seal, seal_sha256), encoding="utf-8", newline="\n"
    )
    return seal, True


def load_seal(root: Path) -> dict[str, Any]:
    path = verification_path(root) / "seal.json"
    if not path.is_file():
        raise FileNotFoundError(f"verification seal not found: {path}; run 'verify seal' first")
    value = read_json(path)
    if not isinstance(value, dict) or value.get("version") != CURRENT_VERSION:
        raise SchemaError("seal is not artifact schema v1")
    return value


def seal_sha256(root: Path) -> str:
    return sha256_file(verification_path(root) / "seal.json")


def validate_seal_state(
    root: Path, plan: dict[str, Any], profile: dict[str, Any], seal: dict[str, Any] | None = None
) -> list[str]:
    root = root.resolve()
    issues: list[str] = []
    try:
        validate_plan(plan)
        validate_profile(profile)
    except SchemaError as exc:
        return [str(exc)]
    if seal is None:
        try:
            seal = load_seal(root)
        except (FileNotFoundError, SchemaError) as exc:
            return [str(exc)]
    if seal.get("repository_root") != str(root):
        issues.append("sealed repository root does not match the active root")
    if seal.get("plan_sha256") != sha256_json(plan):
        issues.append("plan digest does not match the seal")
    if seal.get("profile_sha256") != sha256_json(profile):
        issues.append("repo profile digest does not match the seal")
    for relative, expected in seal.get("artifact_sha256", {}).items():
        path = (root / relative).resolve()
        if not path.is_file():
            issues.append(f"sealed artifact is missing: {relative}")
        elif sha256_file(path) != expected:
            issues.append(f"sealed artifact changed: {relative}")
    current = capture_paths_snapshot(root, seal.get("protected_paths", []))
    if sha256_json(current) != seal.get("protected_snapshot_sha256"):
        issues.append("protected repository state differs from the seal")
    return issues
