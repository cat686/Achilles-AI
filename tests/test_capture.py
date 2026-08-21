from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from goal_verifier.capture import capture_command, record_static_evidence
from goal_verifier.evidence import list_evidence, load_profile, verification_path
from goal_verifier.schema import SchemaError
from goal_verifier.sealing import load_seal

from tests.helpers import initialize_root, obligation, requirement


class CaptureTests(unittest.TestCase):
    def _capture(self, root: Path, plan: dict, requirement_id: str = "R1", obligation_id: str = "R1-O1") -> dict:
        return capture_command(
            root=root,
            plan=plan,
            profile=load_profile(root),
            seal=load_seal(root),
            requirement_id=requirement_id,
            obligation_id=obligation_id,
        )

    def test_stdout_stderr_exit_code_and_duration_are_stored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = [sys.executable, "-B", "-c", "import sys; print('out'); print('err', file=sys.stderr)"]
            plan = initialize_root(root, [requirement(obligations=[obligation(argv=command)])])
            evidence = self._capture(root, plan)
            directory = verification_path(root)
            self.assertEqual((directory / evidence["stdout_path"]).read_text(encoding="utf-8"), "out\n")
            self.assertEqual((directory / evidence["stderr_path"]).read_text(encoding="utf-8"), "err\n")
            self.assertEqual(evidence["exit_code"], 0)
            self.assertGreaterEqual(evidence["duration_seconds"], 0)
            self.assertEqual(evidence["assessment"], "SUPPORTS")
            self.assertIn("git_commit", evidence)
            self.assertIn("git_dirty", evidence)
            self.assertEqual(len(list_evidence(root)), 1)

    def test_failed_command_still_creates_contradictory_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = [sys.executable, "-B", "-c", "import sys; print('failure'); sys.exit(7)"]
            plan = initialize_root(root, [requirement(obligations=[obligation(argv=command)])])
            evidence = self._capture(root, plan)
            self.assertEqual(evidence["exit_code"], 7)
            self.assertEqual(evidence["assessment"], "CONTRADICTS")
            self.assertTrue((verification_path(root) / "evidence" / "E0001.json").is_file())

    def test_command_that_cannot_start_is_inconclusive_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            planned = obligation(argv=["definitely-not-a-real-executable-achilles-ai"])
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertEqual(evidence["status"], "EXECUTION_ERROR")
            self.assertIsNone(evidence["exit_code"])
            self.assertEqual(evidence["assessment"], "INCONCLUSIVE")
            stderr = verification_path(root) / evidence["stderr_path"]
            self.assertIn("Error", stderr.read_text(encoding="utf-8"))

    def test_invalid_json_is_contradictory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            planned = obligation(
                argv=[sys.executable, "-B", "-c", "print('not-json')"],
                oracle={"kind": "stdout_json", "expected_exit_code": 0},
            )
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertEqual(evidence["exit_code"], 0)
            self.assertEqual(evidence["assessment"], "CONTRADICTS")

    def test_static_evidence_records_path_line_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "README.md"
            source.write_text("documented option\n", encoding="utf-8")
            plan = initialize_root(
                root, [requirement(obligations=[obligation("R1-O1", "STATIC")])]
            )
            evidence = record_static_evidence(
                root=root,
                plan=plan,
                profile=load_profile(root),
                seal=load_seal(root),
                requirement_id="R1",
                obligation_id="R1-O1",
                description="The option is documented.",
                assessment="SUPPORTS",
            )
            self.assertEqual(evidence["source_path"], "README.md")
            self.assertEqual(evidence["line"], "1")
            self.assertRegex(evidence["source_sha256"], r"^[0-9a-f]{64}$")

    def test_type_must_match_the_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(root, [requirement()])
            with self.assertRaises(SchemaError):
                record_static_evidence(
                    root=root,
                    plan=plan,
                    profile=load_profile(root),
                    seal=load_seal(root),
                    requirement_id="R1",
                    obligation_id="R1-O1",
                    description="Wrong type",
                    assessment="INCONCLUSIVE",
                )

    def test_differential_compares_with_sealed_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            planned = obligation(
                "R1-O1",
                "DIFFERENTIAL",
                argv=[sys.executable, "-B", "-c", "import sys; sys.stdout.buffer.write(b'baseline\\n')"],
            )
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertEqual(evidence["assessment"], "SUPPORTS")

    def test_performance_is_evaluated_from_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            planned = obligation(
                "R1-O1",
                "PERFORMANCE",
                argv=[sys.executable, "-B", "-c", "print('{\"value\": 10, \"runs\": 3}')"],
            )
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertEqual(evidence["assessment"], "SUPPORTS")


if __name__ == "__main__":
    unittest.main()
