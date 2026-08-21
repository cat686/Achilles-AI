"""Canonical digests and repository-relative path helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .schema import SchemaError


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_relative_file(root: Path, relative: str, label: str = "artifact") -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SchemaError(f"{label} must remain inside the repository root: {relative}") from exc
    if not path.is_file():
        raise SchemaError(f"{label} is not a file: {relative}")
    return path
