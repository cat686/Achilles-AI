from __future__ import annotations

import unittest

from goal_verifier.schema import SchemaError, validate_evidence, validate_plan, validate_verdict

from tests.helpers import requirement


class SchemaTests(unittest.TestCase):
    def _plan(self) -> dict:
        return {
            "version": "1",
            "goal": "A concrete goal",
            "created_at": "2026-01-01T00:00:00Z",
            "repository": {"root": "/repo", "git_commit": None, "worktree_dirty": None},
            "requirements": [requirement()],
        }

    def test_valid_plan_is_accepted(self) -> None:
        plan = {
            "version": "1",
            "goal": "A concrete goal",
            "created_at": "2026-01-01T00:00:00Z",
            "repository": {"root": "/repo", "git_commit": None, "worktree_dirty": None},
            "requirements": [requirement()],
        }
        self.assertIs(validate_plan(plan), plan)

    def test_invalid_verification_type_is_rejected(self) -> None:
        plan = {
            "version": "1",
            "goal": "A concrete goal",
            "created_at": "2026-01-01T00:00:00Z",
            "repository": {"root": "/repo", "git_commit": None, "worktree_dirty": None},
            "requirements": [requirement()],
        }
        plan["requirements"][0]["obligations"][0]["type"] = "MAGIC"
        with self.assertRaises(SchemaError):
            validate_plan(plan)

    def test_invalid_verdict_is_rejected(self) -> None:
        with self.assertRaises(SchemaError):
            validate_verdict("SUCCESS")

    def test_valid_executable_evidence_is_accepted(self) -> None:
        evidence = {
            "version": "1",
            "id": "E0001",
            "session_id": "session",
            "seal_sha256": "a" * 64,
            "requirement_id": "R1",
            "obligation_id": "R1-O1",
            "type": "TEST",
            "source": "existing_test",
            "command": "python test.py",
            "command_args": ["python", "test.py"],
            "cwd": "/repo",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "duration_seconds": 1.0,
            "exit_code": 0,
            "stdout_path": "evidence/E0001.stdout.txt",
            "stderr_path": "evidence/E0001.stderr.txt",
            "fs_events_path": "evidence/E0001.fs-events.json",
            "stdout_sha256": "a" * 64,
            "stderr_sha256": "b" * 64,
            "fs_events_sha256": "c" * 64,
            "git_commit": None,
            "git_dirty": None,
            "environment": {},
            "status": "EXECUTED",
            "assessment": "SUPPORTS",
            "integrity": {"valid": True},
        }
        self.assertIs(validate_evidence(evidence), evidence)

    def test_human_evidence_cannot_force_support(self) -> None:
        evidence = {
            "version": "1",
            "id": "E0001",
            "session_id": "session",
            "seal_sha256": "a" * 64,
            "requirement_id": "R1",
            "obligation_id": "R1-O1",
            "type": "HUMAN",
            "source": "manual",
            "command": None,
            "git_commit": None,
            "git_dirty": None,
            "environment": {},
            "status": "RECORDED",
            "assessment": "SUPPORTS",
        }
        with self.assertRaises(SchemaError):
            validate_evidence(evidence)

    def test_unknown_obligation_field_is_rejected(self) -> None:
        plan = self._plan()
        plan["requirements"][0]["obligations"][0]["unexpected"] = True
        with self.assertRaisesRegex(SchemaError, "unknown fields"):
            validate_plan(plan)

    def test_artifact_path_escape_is_rejected(self) -> None:
        plan = self._plan()
        plan["requirements"][0]["obligations"][0]["experiment"]["artifacts"] = ["../test.py"]
        with self.assertRaisesRegex(SchemaError, "repository-relative"):
            validate_plan(plan)

    def test_differential_requires_differential_oracle(self) -> None:
        plan = self._plan()
        obligation_value = plan["requirements"][0]["obligations"][0]
        obligation_value["type"] = "DIFFERENTIAL"
        with self.assertRaisesRegex(SchemaError, "not valid"):
            validate_plan(plan)

    def test_non_finite_performance_threshold_is_rejected(self) -> None:
        plan = self._plan()
        obligation_value = plan["requirements"][0]["obligations"][0]
        obligation_value["type"] = "PERFORMANCE"
        obligation_value["oracle"] = {
            "kind": "performance",
            "expected_exit_code": 0,
            "metric_pointer": "/value",
            "runs_pointer": "/runs",
            "operator": "lt",
            "threshold": float("nan"),
            "minimum_runs": 1,
            "method": "benchmark",
            "unit": "ms",
        }
        with self.assertRaisesRegex(SchemaError, "finite number"):
            validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
