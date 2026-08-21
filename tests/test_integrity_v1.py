from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from goal_verifier.capture import capture_command
from goal_verifier.evidence import load_profile, verification_path
from goal_verifier.report import generate_reports
from goal_verifier.sealing import load_seal

from tests.helpers import initialize_root, obligation, requirement


class PerExperimentIntegrityTests(unittest.TestCase):
    def _capture(self, root: Path, plan: dict) -> dict:
        return capture_command(
            root=root,
            plan=plan,
            profile=load_profile(root),
            seal=load_seal(root),
            requirement_id="R1",
            obligation_id="R1-O1",
        )

    def test_modify_then_restore_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "production.txt").write_text("original\n", encoding="utf-8")
            script = (
                "from pathlib import Path; "
                "p=Path('production.txt'); old=p.read_text(); "
                "p.write_text('temporary'); p.write_text(old)"
            )
            planned = obligation(argv=[sys.executable, "-B", "-c", script])
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertEqual((root / "production.txt").read_text(encoding="utf-8"), "original\n")
            self.assertFalse(evidence["integrity"]["valid"])
            self.assertTrue(evidence["integrity"]["protected_events"])
            self.assertEqual(evidence["assessment"], "INCONCLUSIVE")

    def test_new_build_output_is_allowed_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = "from pathlib import Path; Path('build').mkdir(); Path('build/output.bin').write_bytes(b'ok')"
            planned = obligation(argv=[sys.executable, "-B", "-c", script])
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertTrue(evidence["integrity"]["valid"])
            self.assertEqual(evidence["assessment"], "SUPPORTS")
            report = generate_reports(root, plan)
            self.assertEqual(report["overall_verdict"], "PASS")
            self.assertIn("build/output.bin", report["integrity"]["non_verification_changes"]["added"])

    def test_child_write_inside_verification_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = "from pathlib import Path; Path('.verification/tmp/attack.txt').write_text('x')"
            planned = obligation(argv=[sys.executable, "-B", "-c", script])
            plan = initialize_root(root, [requirement(obligations=[planned])])
            evidence = self._capture(root, plan)
            self.assertFalse(evidence["integrity"]["valid"])
            self.assertTrue(evidence["integrity"]["protected_events"])
            self.assertEqual(evidence["assessment"], "INCONCLUSIVE")

    def test_stdout_tampering_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = initialize_root(root, [requirement()])
            evidence = self._capture(root, plan)
            stdout = verification_path(root) / evidence["stdout_path"]
            stdout.write_bytes(b"tampered")
            report = generate_reports(root, plan)
            self.assertEqual(report["verification_state"], "STALE")
            self.assertEqual(report["overall_verdict"], "UNKNOWN")
            self.assertTrue(any("digest mismatch" in item["reason"] for item in report["invalid_evidence"]))


if __name__ == "__main__":
    unittest.main()
