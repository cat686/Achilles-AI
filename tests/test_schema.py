from __future__ import annotations

import unittest

from goal_verifier.schema import SchemaError, validate_evidence, validate_plan, validate_verdict

from tests.helpers import requirement


class SchemaTests(unittest.TestCase):
    def test_valid_plan_is_accepted(self) -> None:
        plan = {
            "version": "0",
            "goal": "A concrete goal",
            "created_at": "2026-01-01T00:00:00Z",
            "repository": {"root": "/repo", "git_commit": None, "worktree_dirty": None},
            "requirements": [requirement()],
        }
        self.assertIs(validate_plan(plan), plan)

    def test_invalid_verification_type_is_rejected(self) -> None:
        plan = {
            "version": "0",
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
            "id": "E0001",
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
            "git_commit": None,
            "git_dirty": None,
            "environment": {},
            "status": "EXECUTED",
            "assessment": "SUPPORTS",
        }
        self.assertIs(validate_evidence(evidence), evidence)

    def test_human_evidence_cannot_force_support(self) -> None:
        evidence = {
            "id": "E0001",
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


if __name__ == "__main__":
    unittest.main()

