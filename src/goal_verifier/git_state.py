"""Git metadata and repository-integrity snapshots."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def capture_git_state(root: Path) -> dict[str, Any]:
    root = root.resolve()
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return {
            "available": False,
            "commit": None,
            "dirty": None,
            "status_porcelain": [],
            "error": inside.stderr.strip() or "not a Git worktree",
        }
    commit_result = _git(root, "rev-parse", "HEAD")
    status_result = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    status_lines = status_result.stdout.splitlines() if status_result.returncode == 0 else []
    return {
        "available": True,
        "commit": commit_result.stdout.strip() if commit_result.returncode == 0 else None,
        "dirty": bool(status_lines),
        "status_porcelain": status_lines,
        "error": None if commit_result.returncode == 0 and status_result.returncode == 0 else (
            commit_result.stderr.strip() or status_result.stderr.strip() or "unable to read Git state"
        ),
    }


def capture_tracked_paths(root: Path) -> list[str] | None:
    """Return normalized tracked paths, or None outside a usable Git worktree."""
    state = capture_git_state(root)
    if not state["available"]:
        return None
    result = _git(root.resolve(), "ls-files", "-z")
    if result.returncode != 0:
        return None
    return sorted(item.replace("\\", "/") for item in result.stdout.split("\0") if item)


def _excluded(relative: Path) -> bool:
    return bool(relative.parts) and relative.parts[0] in {".git", ".verification"}


def _walk_files(root: Path) -> Iterable[Path]:
    for directory, names, files in os.walk(root):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(root)
        names[:] = [name for name in names if not _excluded(relative_directory / name)]
        for name in files:
            path = directory_path / name
            if not _excluded(path.relative_to(root)):
                yield path


def capture_file_snapshot(root: Path) -> dict[str, Any]:
    """Hash every non-verification file so already-dirty files remain detectable."""
    root = root.resolve()
    files: dict[str, str] = {}
    errors: list[str] = []
    for path in sorted(_walk_files(root), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[relative] = digest.hexdigest()
        except OSError as exc:
            errors.append(f"{relative}: {exc}")
    return {"algorithm": "sha256", "files": files, "errors": errors}


def capture_paths_snapshot(root: Path, relative_paths: Iterable[str]) -> dict[str, Any]:
    """Hash an explicit protected-path set, including missing-path state."""
    root = root.resolve()
    files: dict[str, str] = {}
    missing: list[str] = []
    errors: list[str] = []
    for relative in sorted(set(relative_paths)):
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"{relative}: path escapes repository root")
            continue
        if not candidate.exists():
            missing.append(relative)
            continue
        if not candidate.is_file():
            errors.append(f"{relative}: protected path is not a regular file")
            continue
        try:
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[relative] = digest.hexdigest()
        except OSError as exc:
            errors.append(f"{relative}: {exc}")
    return {"algorithm": "sha256", "files": files, "missing": missing, "errors": errors}


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    before_files = before.get("files", {})
    after_files = after.get("files", {})
    before_paths = set(before_files)
    after_paths = set(after_files)
    return {
        "added": sorted(after_paths - before_paths),
        "modified": sorted(path for path in before_paths & after_paths if before_files[path] != after_files[path]),
        "deleted": sorted(before_paths - after_paths),
    }


def has_changes(changes: dict[str, list[str]]) -> bool:
    return any(changes.get(kind) for kind in ("added", "modified", "deleted"))
