"""Run the PASS, FAIL, and UNKNOWN Version 0 demos in temporary copies."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from goal_verifier.cli import main
from goal_verifier.evidence import read_json


FIXTURES = {"pass_cli": "PASS", "fail_cli": "FAIL", "unknown_cli": "UNKNOWN"}


def run_fixture(source: Path, expected: str) -> str:
    temporary = tempfile.mkdtemp(prefix=f"achilles-ai-{source.name}-")
    root = Path(temporary) / source.name
    shutil.copytree(source, root)
    arguments = [
        "--root",
        str(root),
        "init",
        "--goal",
        (root / "goal.txt").read_text(encoding="utf-8").strip(),
        "--requirements",
        str(root / "requirements.json"),
        "--profile",
        str(root / "repo_profile.json"),
    ]
    if main(arguments) != 0:
        raise RuntimeError(f"unable to initialize {source.name}")
    if source.name != "unknown_cli":
        result = main(
            [
                "--root",
                str(root),
                "run",
                "--requirement",
                "R1",
                "--obligation",
                "R1-O1",
                "--type",
                "TEST",
                "--source",
                "existing_test",
                "--expect-exit-code",
                "0",
                "--",
                sys.executable,
                "-B",
                "test_acceptance.py",
            ]
        )
        if result != 0:
            raise RuntimeError(f"verifier failed to capture {source.name}")
    if main(["--root", str(root), "report"]) != 0:
        raise RuntimeError(f"unable to report {source.name}")
    report = read_json(root / ".verification" / "report.json")
    actual = report["overall_verdict"]
    if actual != expected:
        raise AssertionError(f"{source.name}: expected {expected}, observed {actual}")
    markdown = (root / ".verification" / "report.md").read_text(encoding="utf-8")
    if expected in {"PASS", "FAIL"} and "E0001" not in markdown:
        raise AssertionError(f"{source.name}: verdict is not traceable to E0001")
    return f"{source.name}: {actual} ({root / '.verification' / 'report.md'})"


def main_demo() -> int:
    examples = Path(__file__).resolve().parent
    for name, expected in FIXTURES.items():
        print(run_fixture(examples / name, expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_demo())
