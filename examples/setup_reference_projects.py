"""Checkout the pinned Click and Cookiecutter reference repositories."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


PROJECTS = {
    "click": (
        "https://github.com/pallets/click.git",
        "2c8cd3ac958a7eb316d67f2d316c27086c4c0369",
    ),
    "cookiecutter": (
        "https://github.com/cookiecutter/cookiecutter.git",
        "c88fbe921c97c58b65f1883ba90a0ab53cc91b34",
    ),
}


def run(*argv: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def ensure_project(examples: Path, name: str, *, check_only: bool) -> None:
    url, commit = PROJECTS[name]
    target = examples / name
    if not target.exists():
        if check_only:
            raise RuntimeError(f"{name}: missing {target}")
        run("git", "init", str(target))
        run("git", "remote", "add", "origin", url, cwd=target)
        run("git", "fetch", "--depth", "1", "origin", commit, cwd=target)
        run("git", "checkout", "--detach", "FETCH_HEAD", cwd=target)

    if not (target / ".git").exists():
        raise RuntimeError(f"{name}: {target} exists but is not a Git worktree")
    actual = run("git", "rev-parse", "HEAD", cwd=target)
    if actual != commit:
        raise RuntimeError(f"{name}: expected {commit}, found {actual}")
    dirty = run("git", "status", "--porcelain", "--untracked-files=no", cwd=target)
    if dirty:
        raise RuntimeError(f"{name}: tracked files are dirty:\n{dirty}")
    print(f"{name}: ready at {commit}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate existing checkouts without cloning")
    args = parser.parse_args()
    examples = Path(__file__).resolve().parent
    for name in PROJECTS:
        ensure_project(examples, name, check_only=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
