"""Persistence helpers for plans and evidence artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .schema import validate_evidence, validate_plan


VERIFICATION_DIRECTORY = ".verification"


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


def load_plan(root: Path) -> dict[str, Any]:
    path = verification_path(root) / "plan.json"
    if not path.is_file():
        raise FileNotFoundError(f"verification plan not found: {path}; run 'verify init' first")
    return validate_plan(read_json(path))


def list_evidence(root: Path) -> list[dict[str, Any]]:
    evidence_directory = verification_path(root) / "evidence"
    if not evidence_directory.is_dir():
        return []
    values = []
    for path in sorted(evidence_directory.glob("E*.json")):
        values.append(validate_evidence(read_json(path)))
    return values


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
    write_json(path, value)
    return path

