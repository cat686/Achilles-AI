"""Persistence helpers for plans and evidence artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .digest import sha256_file, sha256_json
from .schema import CURRENT_VERSION, SchemaError, validate_evidence, validate_plan, validate_profile


VERIFICATION_DIRECTORY = ".verification"


def _evidence_json_paths(directory: Path) -> list[Path]:
    return [path for path in sorted(directory.glob("E*.json")) if re.fullmatch(r"E\d{4,}\.json", path.name)]


def verification_path(root: Path) -> Path:
    return root.resolve() / VERIFICATION_DIRECTORY


def create_layout(root: Path) -> Path:
    directory = verification_path(root)
    (directory / "evidence").mkdir(parents=True, exist_ok=True)
    (directory / "generated").mkdir(exist_ok=True)
    (directory / "tmp").mkdir(exist_ok=True)
    return directory


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = path.parent
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=temporary_directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_plan(root: Path, *, allow_legacy: bool = False) -> dict[str, Any]:
    path = verification_path(root) / "plan.json"
    if not path.is_file():
        raise FileNotFoundError(f"verification plan not found: {path}; run 'verify init' first")
    return validate_plan(read_json(path), allow_legacy=allow_legacy)


def load_profile(root: Path) -> dict[str, Any]:
    path = verification_path(root) / "repo_profile.json"
    if not path.is_file():
        raise FileNotFoundError(f"repository profile not found: {path}; run 'verify init' first")
    return validate_profile(read_json(path))


def list_evidence(root: Path, *, allow_legacy: bool = False) -> list[dict[str, Any]]:
    evidence_directory = verification_path(root) / "evidence"
    if not evidence_directory.is_dir():
        return []
    values = []
    for path in _evidence_json_paths(evidence_directory):
        values.append(validate_evidence(read_json(path), allow_legacy=allow_legacy))
    return values


def list_evidence_with_errors(
    root: Path, *, allow_legacy: bool = False
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    evidence_directory = verification_path(root) / "evidence"
    if not evidence_directory.is_dir():
        return [], []
    values: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in _evidence_json_paths(evidence_directory):
        try:
            values.append(validate_evidence(read_json(path), allow_legacy=allow_legacy))
        except (OSError, json.JSONDecodeError, SchemaError) as exc:
            errors.append({"id": path.stem, "reason": str(exc)})
    return values, errors


def next_evidence_id(root: Path) -> str:
    largest = 0
    evidence_directory = verification_path(root) / "evidence"
    for path in evidence_directory.glob("E*.json"):
        suffix = path.stem[1:]
        if suffix.isdigit():
            largest = max(largest, int(suffix))
    return f"E{largest + 1:04d}"


def save_evidence(root: Path, value: dict[str, Any]) -> Path:
    validate_evidence(value)
    path = verification_path(root) / "evidence" / f"{value['id']}.json"
    if path.exists():
        raise FileExistsError(f"evidence already exists: {path}")
    ledger_path = verification_path(root) / "ledger.json"
    if not ledger_path.is_file():
        raise FileNotFoundError("sealed evidence ledger is missing; run 'verify seal' first")
    ledger = read_json(ledger_path)
    if ledger.get("version") != CURRENT_VERSION or ledger.get("session_id") != value.get("session_id"):
        raise SchemaError("evidence does not belong to the sealed ledger session")
    write_json(path, value)
    previous = ledger["entries"][-1]["entry_sha256"] if ledger["entries"] else ledger["seal_sha256"]
    entry = {
        "id": value["id"],
        "evidence_sha256": sha256_file(path),
        "previous_digest": previous,
    }
    entry["entry_sha256"] = sha256_json(entry)
    ledger["entries"].append(entry)
    write_json(ledger_path, ledger)
    return path


def validate_ledger(
    root: Path, *, session_id: str, seal_sha256: str
) -> tuple[set[str], list[dict[str, str]], str]:
    ledger_path = verification_path(root) / "ledger.json"
    if not ledger_path.is_file():
        return set(), [{"id": "ledger", "reason": "ledger.json is missing"}], seal_sha256
    try:
        ledger = read_json(ledger_path)
    except (OSError, json.JSONDecodeError) as exc:
        return set(), [{"id": "ledger", "reason": str(exc)}], seal_sha256
    errors: list[dict[str, str]] = []
    valid: set[str] = set()
    if ledger.get("version") != CURRENT_VERSION:
        errors.append({"id": "ledger", "reason": "ledger version is not v1"})
    if ledger.get("session_id") != session_id:
        errors.append({"id": "ledger", "reason": "ledger session does not match the seal"})
    if ledger.get("seal_sha256") != seal_sha256:
        errors.append({"id": "ledger", "reason": "ledger genesis does not match the seal"})
    previous = seal_sha256
    seen: set[str] = set()
    for raw_entry in ledger.get("entries", []):
        entry = dict(raw_entry) if isinstance(raw_entry, dict) else {}
        evidence_id = str(entry.get("id", "ledger-entry"))
        entry_digest = entry.pop("entry_sha256", None)
        entry_valid = True
        if evidence_id in seen:
            errors.append({"id": evidence_id, "reason": "duplicate ledger entry"})
            entry_valid = False
        seen.add(evidence_id)
        if entry.get("previous_digest") != previous:
            errors.append({"id": evidence_id, "reason": "broken ledger hash chain"})
            entry_valid = False
        if entry_digest != sha256_json(entry):
            errors.append({"id": evidence_id, "reason": "ledger entry digest mismatch"})
            entry_valid = False
        evidence_path = verification_path(root) / "evidence" / f"{evidence_id}.json"
        if not evidence_path.is_file():
            errors.append({"id": evidence_id, "reason": "ledger evidence file is missing"})
            entry_valid = False
        elif entry.get("evidence_sha256") != sha256_file(evidence_path):
            errors.append({"id": evidence_id, "reason": "evidence JSON digest mismatch"})
            entry_valid = False
        if entry_valid:
            valid.add(evidence_id)
        previous = entry_digest or previous
    disk_ids = {path.stem for path in _evidence_json_paths(verification_path(root) / "evidence")}
    for evidence_id in sorted(disk_ids - seen):
        errors.append({"id": evidence_id, "reason": "evidence is not present in the sealed ledger"})
    return valid, errors, previous
